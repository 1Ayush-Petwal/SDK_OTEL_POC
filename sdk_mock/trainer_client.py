"""
Mock of the Kubeflow TrainerClient, instrumented with the OpenTelemetry API.

IMPORTANT: This module depends ONLY on opentelemetry-api (not opentelemetry-sdk).
This keeps the Kubeflow SDK lightweight — users who don't configure a
TracerProvider will get a no-op tracer and zero overhead.
"""

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .propagator import inject_context_to_env

# Library-level tracer — uses the API only.
tracer = trace.get_tracer("kubeflow-sdk-mock")


class MockTrainerClient:
    """
    Simulates the Kubeflow Training SDK's TrainerClient.

    When `.train()` is called it:
      1. Opens a span representing the job-submission process.
      2. Records GenAI and Kubeflow-specific attributes on the span.
      3. Generates a TRACEPARENT env var that would be injected into
         the Kubernetes Pod spec so the remote job inherits the trace.
    """

    def train(
        self,
        trainer_func: str = "default_train_script",
        model_name: str = "llama-3",
    ) -> str:
        """Submit a mock training job and return a fake job ID."""

        with tracer.start_as_current_span("trainer.submit_job") as span:
            # ── GenAI semantic conventions ──
            span.set_attribute("gen_ai.request.model", model_name)
            span.set_attribute("gen_ai.system", "kubeflow-training")

            # ── Kubeflow-specific attributes ──
            span.set_attribute("kubeflow.job_type", "PyTorchJob")
            span.set_attribute("kubeflow.trainer_func", trainer_func)

            # ── Context propagation (the hard part) ──
            pod_env_vars = inject_context_to_env()

            print(f"  📦  Submitting job for model '{model_name}'...")
            print(f"  🔗  Injecting TRACEPARENT: {pod_env_vars.get('TRACEPARENT')}")

            # Simulate successful K8s API call
            job_id = "job-xyz-123"
            span.set_attribute("kubeflow.job_id", job_id)
            span.set_status(Status(StatusCode.OK))

            return job_id
