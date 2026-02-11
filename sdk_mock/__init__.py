"""
sdk_mock — A mock of the Kubeflow Training SDK, instrumented with OpenTelemetry.

This package uses only the opentelemetry-api (NOT the SDK), keeping the
library lightweight for users who don't want to enable observability.
"""

from .trainer_client import MockTrainerClient

__all__ = ["MockTrainerClient"]
