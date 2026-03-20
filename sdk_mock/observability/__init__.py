"""Shared observability primitives for the Kubeflow SDK mock.

Library code calls make_tracer() / make_meter() rather than the OTel globals
directly so we have a single place to set the instrumentation scope, version,
and schema URL.

Depends on opentelemetry-api only — no SDK import here.
"""
from opentelemetry import trace, metrics

INSTRUMENTATION_SCOPE = "kubeflow.sdk"
SCHEMA_URL = "https://opentelemetry.io/schemas/1.24.0"
_VERSION = "0.2.0"


def make_tracer() -> trace.Tracer:
    """Return a Tracer bound to the Kubeflow SDK instrumentation scope."""
    return trace.get_tracer(INSTRUMENTATION_SCOPE, _VERSION, schema_url=SCHEMA_URL)


def make_meter() -> metrics.Meter:
    """Return a Meter bound to the Kubeflow SDK instrumentation scope."""
    return metrics.get_meter(INSTRUMENTATION_SCOPE, _VERSION, schema_url=SCHEMA_URL)
