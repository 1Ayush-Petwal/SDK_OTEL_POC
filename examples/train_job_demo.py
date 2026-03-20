#!/usr/bin/env python3
"""
train_job_demo.py — End-user demo for the Kubeflow OTel PoC.

This script is the *application* side:
  - It configures an OpenTelemetry TracerProvider (SDK + exporter).
  - It calls MockTrainerClient, which uses the API only.

Running it produces a three-span trace:

    fine_tune_workflow                 [app tracer, INTERNAL]
      └── MockTrainerClient.train      [sdk, INTERNAL]
            └── MockKubernetesBackend.train  [sdk, CLIENT]

Usage:
    # Spans printed to console (no Docker needed):
    python examples/train_job_demo.py

    # Spans sent to Jaeger via OTel Collector:
    docker compose up -d
    python examples/train_job_demo.py
    # Open http://localhost:16686 — service: kubeflow-training-demo
"""
import os
import socket
import sys

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# ── Add project root to sys.path so sdk_mock is importable ──────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sdk_mock import MockTrainerClient  # noqa: E402


def _collector_available(host: str = "localhost", port: int = 4317) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _build_provider() -> tuple[TracerProvider, str]:
    resource = Resource.create({
        "service.name": "kubeflow-training-demo",
        "service.version": "0.2.0",
    })
    provider = TracerProvider(resource=resource)

    if _collector_available():
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
        target = "OTLP → Collector → Jaeger"
    else:
        exporter = ConsoleSpanExporter()
        target = "Console (OTel Collector not reachable on :4317)"

    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider, target


def run_demo() -> None:
    provider, target = _build_provider()
    trace.set_tracer_provider(provider)

    print(f"\nKubeflow OTel PoC  —  exporting to: {target}\n")

    client = MockTrainerClient(namespace="ml-team")
    app_tracer = trace.get_tracer("kubeflow-training-demo")

    with app_tracer.start_as_current_span("fine_tune_workflow") as root:
        root.set_attribute("workflow.name", "llm-fine-tuning")

        # train() emits two spans beneath this one:
        #   MockTrainerClient.train (INTERNAL) → MockKubernetesBackend.train (CLIENT)
        job_name = client.train(
            trainer_kind="CustomTrainer",
            runtime="torch-distributed",
            num_nodes=2,
            # gen_ai.request.model is set only because we're referencing a model URI
            model_name="hf://meta-llama/Llama-3",
        )
        root.add_event("job_submitted", {"kubeflow.job.name": job_name})
        print(f"  Job submitted : {job_name}")

        job = client.get_job(job_name)
        print(f"  Job status    : {job['status']}")

    provider.force_flush()
    provider.shutdown()

    print("\nDone. Open Jaeger UI → http://localhost:16686  (service: kubeflow-training-demo)\n")


if __name__ == "__main__":
    run_demo()
