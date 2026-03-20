"""Span capture helper for unit tests.

Patches the module-level _tracer objects directly rather than swapping the
global TracerProvider. The OTel SDK only allows set_tracer_provider() once —
after that it warns and does nothing, which breaks multi-test suites. Patching
the tracer references avoids that restriction entirely.
"""
from contextlib import contextmanager
from unittest.mock import patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from sdk_mock.observability import INSTRUMENTATION_SCOPE, _VERSION


@contextmanager
def capture_spans():
    """Capture all spans emitted inside the with-block.

    Yields an InMemorySpanExporter whose .get_finished_spans() can be
    inspected after the block exits.

    Usage::

        with capture_spans() as rec:
            client.train(...)

        spans = rec.get_finished_spans()
        assert "MockTrainerClient.train" in [s.name for s in spans]
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(INSTRUMENTATION_SCOPE, _VERSION)

    with (
        patch("sdk_mock.trainer_client._tracer", tracer),
        patch("sdk_mock.backends.kubernetes_backend._tracer", tracer),
        patch("sdk_mock.backends.local_backend._tracer", tracer),
    ):
        yield exporter

    provider.shutdown()
