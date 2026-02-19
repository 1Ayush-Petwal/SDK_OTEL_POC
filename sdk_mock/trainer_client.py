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

    
    """
    .train() reference comparision:

    from kubeflow/trainer/backends/kubernetes/backend.py import train

    def train(
        self,
        runtime: Optional[Union[str, types.Runtime]] = None,
        initializer: Optional[types.Initializer] = None,
        trainer: Optional[
            Union[types.CustomTrainer, types.CustomTrainerContainer, types.BuiltinTrainer]
        ] = None,
        options: Optional[list] = None,
    ) -> str:
        # Process options to extract configuration
        job_spec = {}
        labels = None
        annotations = None
        name = None
        spec_labels = None
        spec_annotations = None
        trainer_overrides = {}
        pod_template_overrides = None

        if options:
            for option in options:
                option(job_spec, trainer, self)

            metadata_section = job_spec.get("metadata", {})
            labels = metadata_section.get("labels")
            annotations = metadata_section.get("annotations")
            name = metadata_section.get("name")

            # Extract spec-level labels/annotations and other spec configurations
            spec_section = job_spec.get("spec", {})
            spec_labels = spec_section.get("labels")
            spec_annotations = spec_section.get("annotations")
            trainer_overrides = spec_section.get("trainer", {})
            pod_template_overrides = spec_section.get("podTemplateOverrides")

        # Generate unique name for the TrainJob if not provided
        train_job_name = name or (
            random.choice(string.ascii_lowercase)
            + uuid.uuid4().hex[: constants.JOB_NAME_UUID_LENGTH]
        )

        # Build the TrainJob spec using the common _get_trainjob_spec method
        trainjob_spec = self._get_trainjob_spec(
            runtime=runtime,
            initializer=initializer,
            trainer=trainer,
            trainer_overrides=trainer_overrides,
            spec_labels=spec_labels,
            spec_annotations=spec_annotations,
            pod_template_overrides=pod_template_overrides,
        )

        # Build the TrainJob.
        train_job = models.TrainerV1alpha1TrainJob(
            apiVersion=constants.API_VERSION,
            kind=constants.TRAINJOB_KIND,
            metadata=models.IoK8sApimachineryPkgApisMetaV1ObjectMeta(
                name=train_job_name, labels=labels, annotations=annotations
            ),
            spec=trainjob_spec,
        )

        # Create the TrainJob.
        try:
            self.custom_api.create_namespaced_custom_object(
                constants.GROUP,
                constants.VERSION,
                self.namespace,
                constants.TRAINJOB_PLURAL,
                train_job.to_dict(),
            )
        except multiprocessing.TimeoutError as e:
            raise TimeoutError(
                f"Timeout to create {constants.TRAINJOB_KIND}: {self.namespace}/{train_job_name}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to create {constants.TRAINJOB_KIND}: {self.namespace}/{train_job_name}"
            ) from e

        logger.debug(
            f"{constants.TRAINJOB_KIND} {self.namespace}/{train_job_name} has been created"
        )

        return train_job_name
    """
