"""W3C Trace Context injection for pod / container / subprocess environments.

The TRACEPARENT env var lets worker code continue the trace started by the SDK
without any code coupling — workers simply read the env var if they want to
link in. If they ignore it, nothing breaks.

Spec reference: https://opentelemetry.io/docs/specs/otel/context/env-carriers/
"""
from opentelemetry import context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_propagator = TraceContextTextMapPropagator()


def trace_env_vars() -> dict[str, str]:
    """Serialize the active trace context as uppercase env var names.

    Returns a dict like {"TRACEPARENT": "00-<trace_id>-<span_id>-01"} that can
    be merged into a pod spec, container env, or subprocess env dict.

    Returns {} when no active span exists — safe to merge unconditionally.
    """
    carrier: dict[str, str] = {}
    _propagator.inject(carrier, context.get_current())
    return {k.upper(): v for k, v in carrier.items()}
