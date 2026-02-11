"""
Context propagation helpers for Kubeflow Training jobs.

This module demonstrates how the current OpenTelemetry trace context is
serialized into W3C Trace Context format (TRACEPARENT) so that it can be
injected as environment variables into a Kubernetes Pod spec, allowing a
remote training job to continue the same distributed trace.
"""

from opentelemetry import propagate


def inject_context_to_env() -> dict[str, str]:
    """
    Capture the current trace context and return it as environment
    variables suitable for injection into a Kubernetes Pod spec.

    Returns:
        A dict like {"TRACEPARENT": "00-<trace_id>-<span_id>-01"}
    """
    carrier: dict[str, str] = {}
    propagate.inject(carrier)

    # W3C standard uses lowercase 'traceparent',
    # but Kubernetes env vars are conventionally UPPERCASE.
    env_vars: dict[str, str] = {}
    if "traceparent" in carrier:
        env_vars["TRACEPARENT"] = carrier["traceparent"]
    if "tracestate" in carrier:
        env_vars["TRACESTATE"] = carrier["tracestate"]

    return env_vars
