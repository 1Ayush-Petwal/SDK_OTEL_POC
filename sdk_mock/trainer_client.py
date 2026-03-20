"""MockTrainerClient — INTERNAL spans wrapping a backend layer.

Depends on opentelemetry-api only; opentelemetry-sdk is never imported here.
When no TracerProvider is configured the tracer and meter are no-ops with zero
performance overhead.

Span hierarchy produced per operation:

    MockTrainerClient.train       [INTERNAL]   ← what the user called
        └── MockKubernetesBackend.train  [CLIENT]  ← what actually ran

Sub-operations within the backend are span events, not child spans, so traces
stay readable without losing debugging detail.
"""
import time

from opentelemetry.trace import SpanKind, StatusCode

from .backends import MockKubernetesBackend
from .observability import make_meter, make_tracer
from .observability.attributes import (
    BACKEND_KIND,
    ERROR_KIND,
    JOB_NAME,
    JOB_STATUS,
    MODEL_NAME,
    NODE_COUNT,
    OPERATION,
    RUNTIME_NAME,
    TRAINER_KIND,
)

_tracer = make_tracer()
_meter  = make_meter()

# ── Instruments ────────────────────────────────────────────────────────────────
# Metric names use a shorter "kf.*" prefix to distinguish this PoC's scope
# from the full SDK's "kubeflow.*" production namespace.

_jobs_submitted = _meter.create_counter(
    "kf.training.jobs.submitted",
    unit="{job}",
    description="Total training jobs submitted via the SDK.",
)
_op_latency = _meter.create_histogram(
    "kf.training.operation.latency",
    unit="s",
    description="Wall-clock time of each SDK operation.",
)
_jobs_running = _meter.create_up_down_counter(
    "kf.training.jobs.running",
    unit="{job}",
    description="Jobs currently tracked as active.",
)
_failures = _meter.create_counter(
    "kf.training.failures",
    unit="{error}",
    description="Total operation failures, dimensioned by error class and operation.",
)


class MockTrainerClient:
    """Simulates TrainerClient from the Kubeflow Training SDK.

    Each public method opens an INTERNAL span that wraps a backend call.
    The backend creates its own CLIENT span, producing the two-level hierarchy
    visible in trace UIs (Jaeger, Grafana Tempo, etc.).
    """

    def __init__(self, backend=None, namespace: str = "default"):
        self._backend = backend or MockKubernetesBackend(namespace=namespace)

    def train(
        self,
        trainer_kind: str = "CustomTrainer",
        runtime: str = "torch-distributed",
        num_nodes: int = 1,
        model_name: str | None = None,
    ) -> str:
        """Submit a training job and return the job name."""
        t0 = time.perf_counter()
        with _tracer.start_as_current_span(
            "MockTrainerClient.train",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(TRAINER_KIND, trainer_kind)
            span.set_attribute(RUNTIME_NAME, runtime)
            span.set_attribute(NODE_COUNT, num_nodes)

            # Only record gen_ai.request.model when there is actually a model
            # URI present. gen_ai.usage.* attributes are for inference, not training.
            if model_name:
                span.set_attribute(MODEL_NAME, model_name)

            try:
                job_name = self._backend.train(
                    trainer_kind=trainer_kind, runtime=runtime
                )
                span.set_attribute(JOB_NAME, job_name)
                span.set_status(StatusCode.OK)

                _jobs_submitted.add(1, {BACKEND_KIND: "kubernetes", TRAINER_KIND: trainer_kind})
                _jobs_running.add(1, {BACKEND_KIND: "kubernetes"})
                return job_name

            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                _failures.add(
                    1,
                    {OPERATION: "train", ERROR_KIND: type(exc).__name__, BACKEND_KIND: "kubernetes"},
                )
                raise

            finally:
                _op_latency.record(
                    time.perf_counter() - t0,
                    {OPERATION: "train", BACKEND_KIND: "kubernetes"},
                )

    def get_job(self, job_name: str) -> dict:
        """Fetch current job status."""
        t0 = time.perf_counter()
        with _tracer.start_as_current_span(
            "MockTrainerClient.get_job",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(JOB_NAME, job_name)

            try:
                result = self._backend.get_job(job_name)
                span.set_attribute(JOB_STATUS, result["status"])
                span.set_status(StatusCode.OK)
                return result

            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                _failures.add(
                    1,
                    {OPERATION: "get_job", ERROR_KIND: type(exc).__name__, BACKEND_KIND: "kubernetes"},
                )
                raise

            finally:
                _op_latency.record(
                    time.perf_counter() - t0,
                    {OPERATION: "get_job", BACKEND_KIND: "kubernetes"},
                )
