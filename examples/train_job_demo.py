#!/usr/bin/env python3
"""
train_job_demo.py — End-user demo for the Kubeflow OTel PoC.

This script represents the *application* side:
  • It configures an OpenTelemetry TracerProvider (SDK dependency).
  • It calls the instrumented MockTrainerClient (which uses only the API).
  • It records GenAI semantic-convention attributes on the span.

Usage:
    # Without Docker (spans printed to console):
    python examples/train_job_demo.py

    # With Docker (spans sent to Jaeger via OTel Collector):
    docker compose up -d
    python examples/train_job_demo.py
    # Then open http://localhost:16686 to view traces.
"""

import sys
import os

# ── OpenTelemetry SDK configuration (app-side only) ─────────────────────────
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource

# Attempt OTLP export; fall back to console if the collector is unreachable.
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
    export_target = "OTel Collector → Jaeger"
except Exception:
    exporter = ConsoleSpanExporter()
    export_target = "Console (OTLP unavailable)"

# Build the provider with a descriptive service name.
resource = Resource.create({"service.name": "kubeflow-training-demo"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)

# ── Add the project root to sys.path so `sdk_mock` is importable ────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sdk_mock import MockTrainerClient  # noqa: E402


def run_demo() -> None:
    """Simulate an end-user fine-tuning an LLM via the Kubeflow SDK."""

    # Application-level tracer (uses the SDK-configured provider).
    app_tracer = trace.get_tracer("kubeflow-training-demo")

    print(f"\n🚀  Kubeflow OTel PoC — exporting to: {export_target}\n")

    with app_tracer.start_as_current_span("fine_tune_workflow") as workflow_span:
        workflow_span.set_attribute("workflow.name", "llm-fine-tuning")

        client = MockTrainerClient()

        # ── Submit a training job ──
        job_id = client.train(trainer_func="my_lora_script.py", model_name="qwen-7b")
        print(f"  ✅  Job submitted: {job_id}")

        # ── Record GenAI token-usage attributes (semantic conventions) ──
        workflow_span.set_attribute("gen_ai.usage.input_tokens", 1024)
        workflow_span.set_attribute("gen_ai.usage.output_tokens", 256)
        workflow_span.add_event(
            "Fine-tuning started",
            attributes={"gen_ai.request.model": "qwen-7b"},
        )

    # Ensure all spans are flushed before exit.
    provider.force_flush()
    provider.shutdown()

    print("\n🏁  Done — spans flushed.\n")


if __name__ == "__main__":
    run_demo()
