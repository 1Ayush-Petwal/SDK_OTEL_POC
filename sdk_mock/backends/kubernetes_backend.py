"""Mock Kubernetes backend.

Uses SpanKind.CLIENT because submitting to the K8s API is a remote call.

Sub-operations (runtime resolution, spec construction, API submission) are
recorded as span *events* rather than child spans — this keeps traces readable
at two levels deep while still providing enough detail to debug slow calls.
"""
import time
import uuid

from opentelemetry.trace import SpanKind, StatusCode

from sdk_mock.observability import make_tracer
from sdk_mock.observability.attributes import (
    BACKEND_KIND,
    JOB_NAME,
    JOB_STATUS,
    NAMESPACE,
    RUNTIME_NAME,
    TRAINER_KIND,
)
from sdk_mock.observability.propagation import trace_env_vars

_tracer = make_tracer()


class MockKubernetesBackend:
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace

    def train(self, trainer_kind: str, runtime: str, **kwargs) -> str:
        with _tracer.start_as_current_span(
            "MockKubernetesBackend.train",
            kind=SpanKind.CLIENT,
        ) as span:
            span.set_attribute(BACKEND_KIND, "kubernetes")
            span.set_attribute(NAMESPACE, self.namespace)
            span.set_attribute(TRAINER_KIND, trainer_kind)
            span.set_attribute(RUNTIME_NAME, runtime)

            try:
                span.add_event("resolving_runtime")
                time.sleep(0.001)  # simulate runtime lookup latency

                span.add_event("building_job_spec")
                job_name = f"train-{uuid.uuid4().hex[:8]}"

                # Inject trace context — in the real SDK this would be merged
                # into the pod template env vars before create_namespaced_custom_object.
                env_vars = trace_env_vars()
                span.add_event(
                    "traceparent_injected",
                    {"injected_keys": str(list(env_vars.keys()))},
                )

                span.add_event("submitting_to_k8s_api")
                time.sleep(0.002)  # simulate create_namespaced_custom_object latency

                span.set_attribute(JOB_NAME, job_name)
                span.set_status(StatusCode.OK)
                return job_name

            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

    def get_job(self, job_name: str) -> dict:
        with _tracer.start_as_current_span(
            "MockKubernetesBackend.get_job",
            kind=SpanKind.CLIENT,
        ) as span:
            span.set_attribute(BACKEND_KIND, "kubernetes")
            span.set_attribute(NAMESPACE, self.namespace)
            span.set_attribute(JOB_NAME, job_name)

            try:
                time.sleep(0.001)
                status = "Running"
                span.set_attribute(JOB_STATUS, status)
                span.set_status(StatusCode.OK)
                return {"name": job_name, "status": status}

            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise
