"""Unit tests for MockTrainerClient and MockKubernetesBackend span instrumentation.

All assertions use InMemorySpanExporter via the capture_spans() context manager —
no real network calls, no OTel Collector required.

Test categories:
  - SpanHierarchy    — correct names and parent-child wiring
  - SpanKinds        — INTERNAL for client methods, CLIENT for backend methods
  - Attributes       — correct keys and values per operation
  - ErrorRecording   — set_status(ERROR) + record_exception on every failure path
  - NoopBehavior     — SDK works normally when no TracerProvider is configured
  - Propagation      — TRACEPARENT injected as a backend span event
"""
import pytest
from opentelemetry.trace import SpanKind, StatusCode

from sdk_mock.trainer_client import MockTrainerClient
from tests.helpers import capture_spans


def _span(spans, name):
    """Find a single span by name, or return None."""
    return next((s for s in spans if s.name == name), None)


# ── Hierarchy ──────────────────────────────────────────────────────────────────

class TestSpanHierarchy:
    def test_train_emits_client_and_backend_spans(self):
        with capture_spans() as rec:
            MockTrainerClient().train()

        names = {s.name for s in rec.get_finished_spans()}
        assert "MockTrainerClient.train" in names
        assert "MockKubernetesBackend.train" in names

    def test_backend_span_is_child_of_client_span(self):
        with capture_spans() as rec:
            MockTrainerClient().train()

        spans = rec.get_finished_spans()
        client  = _span(spans, "MockTrainerClient.train")
        backend = _span(spans, "MockKubernetesBackend.train")

        assert client is not None
        assert backend is not None
        assert backend.parent.span_id == client.context.span_id

    def test_get_job_emits_two_spans(self):
        with capture_spans() as rec:
            client = MockTrainerClient()
            job_name = client.train()
            client.get_job(job_name)

        names = {s.name for s in rec.get_finished_spans()}
        assert "MockTrainerClient.get_job" in names
        assert "MockKubernetesBackend.get_job" in names


# ── SpanKind ───────────────────────────────────────────────────────────────────

class TestSpanKinds:
    def test_client_span_is_internal(self):
        with capture_spans() as rec:
            MockTrainerClient().train()

        span = _span(rec.get_finished_spans(), "MockTrainerClient.train")
        assert span.kind == SpanKind.INTERNAL

    def test_backend_span_is_client(self):
        with capture_spans() as rec:
            MockTrainerClient().train()

        span = _span(rec.get_finished_spans(), "MockKubernetesBackend.train")
        assert span.kind == SpanKind.CLIENT


# ── Attributes ─────────────────────────────────────────────────────────────────

class TestAttributes:
    def test_train_attributes_on_client_span(self):
        with capture_spans() as rec:
            MockTrainerClient().train(
                trainer_kind="BuiltinTrainer",
                runtime="deepspeed",
                num_nodes=4,
            )

        attrs = _span(rec.get_finished_spans(), "MockTrainerClient.train").attributes
        assert attrs["kubeflow.trainer.kind"] == "BuiltinTrainer"
        assert attrs["kubeflow.runtime.name"] == "deepspeed"
        assert attrs["kubeflow.num_nodes"] == 4

    def test_model_name_set_when_provided(self):
        with capture_spans() as rec:
            MockTrainerClient().train(model_name="hf://meta-llama/Llama-3")

        attrs = _span(rec.get_finished_spans(), "MockTrainerClient.train").attributes
        assert attrs.get("gen_ai.request.model") == "hf://meta-llama/Llama-3"

    def test_model_name_absent_when_not_provided(self):
        with capture_spans() as rec:
            MockTrainerClient().train()

        attrs = _span(rec.get_finished_spans(), "MockTrainerClient.train").attributes
        assert "gen_ai.request.model" not in attrs

    def test_job_name_appears_on_both_spans(self):
        with capture_spans() as rec:
            MockTrainerClient().train()

        spans = rec.get_finished_spans()
        client_attrs  = _span(spans, "MockTrainerClient.train").attributes
        backend_attrs = _span(spans, "MockKubernetesBackend.train").attributes

        assert "kubeflow.job.name" in client_attrs
        assert "kubeflow.job.name" in backend_attrs
        assert client_attrs["kubeflow.job.name"] == backend_attrs["kubeflow.job.name"]

    def test_backend_span_has_namespace(self):
        with capture_spans() as rec:
            MockTrainerClient(namespace="ml-team").train()

        attrs = _span(rec.get_finished_spans(), "MockKubernetesBackend.train").attributes
        assert attrs.get("k8s.namespace.name") == "ml-team"


# ── Error recording ────────────────────────────────────────────────────────────

class TestErrorRecording:
    def _broken_backend(self, exc=RuntimeError("k8s API unavailable")):
        class _Backend:
            def train(self, **_): raise exc
            def get_job(self, job_name): raise exc
        return _Backend()

    def test_train_marks_span_as_error(self):
        with capture_spans() as rec:
            with pytest.raises(RuntimeError):
                MockTrainerClient(backend=self._broken_backend()).train()

        span = _span(rec.get_finished_spans(), "MockTrainerClient.train")
        assert span.status.status_code == StatusCode.ERROR

    def test_train_records_exception_event(self):
        with capture_spans() as rec:
            with pytest.raises(RuntimeError):
                MockTrainerClient(backend=self._broken_backend()).train()

        span = _span(rec.get_finished_spans(), "MockTrainerClient.train")
        assert any(e.name == "exception" for e in span.events)

    def test_get_job_marks_span_as_error(self):
        class _Backend:
            def train(self, **_): return "fake-job"
            def get_job(self, job_name): raise TimeoutError("timeout")

        with capture_spans() as rec:
            with pytest.raises(TimeoutError):
                MockTrainerClient(backend=_Backend()).get_job("fake-job")

        span = _span(rec.get_finished_spans(), "MockTrainerClient.get_job")
        assert span.status.status_code == StatusCode.ERROR
        assert any(e.name == "exception" for e in span.events)


# ── No-op behavior ─────────────────────────────────────────────────────────────

class TestNoopBehavior:
    def test_sdk_works_without_any_provider(self):
        """With no TracerProvider set the SDK must not raise or change behavior."""
        # capture_spans() is intentionally NOT used here — we want the default no-op provider.
        client = MockTrainerClient()
        result = client.train()
        assert result is not None
        assert result.startswith("train-")


# ── Context propagation ────────────────────────────────────────────────────────

class TestContextPropagation:
    def test_traceparent_injected_as_backend_event(self):
        with capture_spans() as rec:
            MockTrainerClient().train()

        backend = _span(rec.get_finished_spans(), "MockKubernetesBackend.train")
        event_names = [e.name for e in backend.events]
        assert "traceparent_injected" in event_names
