"""Mock local-process backend.

Uses SpanKind.INTERNAL (not CLIENT) because spawning a subprocess is a local
operation — there is no remote service being called.
"""
import uuid

from opentelemetry.trace import SpanKind, StatusCode

from sdk_mock.observability import make_tracer
from sdk_mock.observability.attributes import (
    BACKEND_KIND,
    JOB_NAME,
    RUNTIME_NAME,
    TRAINER_KIND,
)
from sdk_mock.observability.propagation import trace_env_vars

_tracer = make_tracer()


class MockLocalProcessBackend:
    def train(self, trainer_kind: str, runtime: str, **kwargs) -> str:
        with _tracer.start_as_current_span(
            "MockLocalProcessBackend.train",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(BACKEND_KIND, "local-process")
            span.set_attribute(TRAINER_KIND, trainer_kind)
            span.set_attribute(RUNTIME_NAME, runtime)

            try:
                job_name = f"local-{uuid.uuid4().hex[:8]}"

                # TRACEPARENT is injected into the subprocess env so the
                # training script can optionally continue the same trace.
                env_vars = trace_env_vars()
                span.add_event(
                    "subprocess_launched",
                    {"traceparent_present": "TRACEPARENT" in env_vars},
                )

                span.set_attribute(JOB_NAME, job_name)
                span.set_status(StatusCode.OK)
                return job_name

            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise
