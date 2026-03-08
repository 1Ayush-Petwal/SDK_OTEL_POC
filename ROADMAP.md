# Kubeflow OpenTelemetry — Implementation Roadmap

---

## Goal: End-to-End visibility into SDK operations

## Exact requirements:

We need to capture: 

- Distrubuted traces
- Metrics
- logs 

There are 4 categories of telemetry:

- Distributed Tracing ( insight into end - end traffic )
- Metrics ( insight into performance / resource consumption )
- Logging ( insight into what your application is doing )
- Health ( insight into availability of running parts )


Across: 

- Pipeline Compilation
- Submission 
- Execution 
- Training Lifecycles

Leveraging existing OpenTelemetry and Generative AI instrumentation patterns:

- Span conventions for model executions 
- Prompt handling 
- Inference steps

Configuring the OTEL option using a config.yaml or its 

What to instrument ?

Semantic conventions are the main source of truth about what information is included on spans produced by web frameworks, RPC clients, databases, messaging clients, infrastructure, and more.

## Guiding Principles

- **API-only in the library.** `sdk/kubeflow/` must never import `opentelemetry-sdk`. Only `opentelemetry-api` is a direct dependency. The no-op tracer provides zero overhead for users who don't configure a provider.
- **Opt-in at the client level.** Each client (`TrainerClient`, `OptimizerClient`, `SparkClient`, `ModelRegistryClient`) exposes `otel_enabled: bool = False`. Users enable it explicitly.
- **OTel semantic conventions first.** Prefer `gen_ai.*` and standard OTel attribute names. Use `kubeflow.*` namespace only for attributes with no standard equivalent.
- **No breaking changes.** Every phase is a backward-compatible addition. Existing call sites continue to work unchanged.

---

## Phase 0 — POC Hardening (now, pre-merge)

**Scope**: Fix the known gaps in `kubeflow-otel-poc/` before using it as a reference for SDK work.

| # | Gap (from POC_Report §3) | Fix |
|---|---|---|
| 3.1 | Missing `SpanKind.CLIENT` on `trainer.submit_job` | Add `kind=SpanKind.CLIENT` to `start_as_current_span` |
| 3.2 | No exception recording | Wrap backend call in `try/except`; call `span.record_exception()` + `set_status(ERROR)` |
| 3.6 | No tracer version / schema URL | Pass `tracer_version` and `schema_url` to `trace.get_tracer()` |

**Files changed**: `sdk_mock/trainer_client.py`
**Deliverable**: A clean, gap-free reference that SDK phases 1–5 will follow exactly.

---

## Phase 1 — SDK Foundation  (`v0.3.x`, weeks 1–2)

**Goal**: Non-breaking groundwork. No user-facing behavioral change.

### 1.1 Add `opentelemetry-api` to `pyproject.toml`

```toml
[project.dependencies]
opentelemetry-api >= 1.25.0          # no-op when provider is absent

[project.optional-dependencies]
otel = [
    "opentelemetry-sdk >= 1.25.0",
    "opentelemetry-exporter-otlp-proto-grpc >= 1.25.0",
]
```

Install: `pip install 'kubeflow[otel]'`

### 1.2 Create `kubeflow/observability/` module

```
kubeflow/observability/
├── __init__.py       # re-exports: get_tracer, inject_context_to_env, inject_context_to_pod_spec
├── tracer.py         # centralized tracer factory (version + schema URL)
├── propagator.py     # W3C context → Kubernetes pod spec (hardened from POC)
└── attributes.py     # semantic attribute name constants (gen_ai.*, kubeflow.*)
```

Key implementation detail in `tracer.py`:

```python
from kubeflow import __version__
_SCHEMA_URL = "https://opentelemetry.io/schemas/1.24.0"

def get_tracer(module_name: str) -> trace.Tracer:
    return trace.get_tracer(module_name, tracer_version=__version__, schema_url=_SCHEMA_URL)
```

### 1.3 Unit tests for `kubeflow/observability/`

```
kubeflow/observability/
├── tracer_test.py
├── propagator_test.py
└── attributes_test.py
```

Test that `inject_context_to_env()` returns an empty dict when no span is active (no-op path) and a valid `TRACEPARENT` string when a real span is active.

### 1.4 Update `CONTRIBUTING.md` and `CLAUDE.md`

Document OTel conventions: span naming (`kubeflow.<module>.<method>`), required attributes, `SpanKind.CLIENT` for all K8s API calls.

**Deliverable**: Standalone PR. Zero behavioral change for existing users.

---

## Phase 2 — Instrument `TrainerClient`  (`v0.4.0`, weeks 3–4)

**Goal**: Full distributed tracing for the most-used client, end-to-end from submission through to the worker pod.

### 2.1 `otel_enabled` flag

```python
# kubeflow/trainer/api/trainer_client.py
class TrainerClient:
    def __init__(self, backend_config=None, *, otel_enabled: bool = False):
        self._tracer = get_tracer("kubeflow.trainer") if otel_enabled else None
```

### 2.2 Instrument all public methods

| Method | Span name | Key attributes |
|---|---|---|
| `train()` | `kubeflow.trainer.train` | `job.name`, `job.runtime`, `job.num_nodes` |
| `get_job()` | `kubeflow.trainer.get_job` | `job.name`, `job.status` |
| `get_job_logs()` | `kubeflow.trainer.get_logs` | `job.name`, `step` |
| `get_job_events()` | `kubeflow.trainer.get_events` | `job.name` |
| `wait_for_job_status()` | `kubeflow.trainer.wait` | `job.name`, `timeout`, `target_status` |
| `delete_job()` | `kubeflow.trainer.delete_job` | `job.name` |
| `list_jobs()` | `kubeflow.trainer.list_jobs` | result `count` |

All spans use `SpanKind.CLIENT`. All wrap the backend call in `try/except` to record exceptions.

### 2.3 Context injection into `KubernetesBackend`

In `kubeflow/trainer/backends/kubernetes/backend.py`, after building the TrainJob spec and before `create_namespaced_custom_object`:

```python
from kubeflow.observability.propagator import inject_context_to_pod_spec

for replica_spec in train_job_spec.get("replicaSpecs", {}).values():
    inject_context_to_pod_spec(replica_spec["template"]["spec"])
```

Apply equivalent injection in `ContainerBackend` and `LocalProcessBackend` (environment variable path).

### 2.4 Tests

- `kubeflow/trainer/api/trainer_client_otel_test.py`
- Use `InMemorySpanExporter` + `SimpleSpanProcessor` — no real network calls.
- Assert span name, `SpanKind`, key attributes, and `StatusCode.OK` on success.
- Assert `StatusCode.ERROR` and an exception event on backend failure.

### 2.5 Example + docs

- `examples/observability/basic_tracing.py` — minimal end-to-end demo.
- `docs/source/observability/quickstart.rst`

**Deliverable**: First OTel-capable release. Full `TrainJob` trace from submission → worker pod.

---

## Phase 3 — All Clients Traced  (`v0.4.x`, weeks 5–6)

**Goal**: Uniform observability across all four SDK clients.

### `OptimizerClient`

| Method | Span name | Key attributes |
|---|---|---|
| `optimize()` | `kubeflow.optimizer.optimize` | `num_trials`, `algorithm`, `objective.metric`, `objective.direction` |
| `get_best_trial()` | `kubeflow.optimizer.get_best_trial` | `job.name`, `best_params` (serialized) |
| `wait_for_job_status()` | `kubeflow.optimizer.wait` | `job.name`, `timeout` |

### `SparkClient`

| Method | Span name | Key attributes |
|---|---|---|
| `connect()` | `kubeflow.spark.connect` | `num_executors`, `resources_per_executor` |
| `submit_job()` | `kubeflow.spark.submit_job` | `job.name` |

### `ModelRegistryClient`

| Method | Span name | Key attributes |
|---|---|---|
| `register_model()` | `kubeflow.hub.register_model` | `model.name`, `model.version`, `model.uri` |
| `get_model()` | `kubeflow.hub.get_model` | `model.name` |

### Cross-client trace continuity

`optimizer.optimize()` → `trainer.train()` → `hub.register_model()` must all share a single `traceID` when called within the same application-level span. This works automatically once each client propagates context correctly — no extra wiring needed.

### W3C Baggage

Propagate `experiment.id`, `project.name`, and `user.id` via W3C Baggage so all downstream spans receive them without manual `set_attribute` calls.

**Deliverable**: End-to-end trace from `optimizer.optimize()` through pod completion and model registration.

---

## Phase 4 — Metrics  (`v0.5.0`, weeks 7–8)

**Goal**: Operational dashboards and alerting without requiring trace sampling.

### `kubeflow/observability/metrics.py`

```python
from opentelemetry import metrics

_meter = metrics.get_meter("kubeflow.sdk", schema_url=_SCHEMA_URL)

jobs_submitted  = _meter.create_counter("kubeflow.trainer.jobs.submitted", unit="1")
jobs_failed     = _meter.create_counter("kubeflow.trainer.jobs.failed",    unit="1")
job_duration    = _meter.create_histogram("kubeflow.trainer.job.duration",  unit="s")
active_jobs     = _meter.create_up_down_counter("kubeflow.trainer.jobs.active", unit="1")
spark_sessions  = _meter.create_up_down_counter("kubeflow.spark.sessions.active", unit="1")
```

Emit from:
- `train()` call-site: increment `jobs_submitted` and `active_jobs`.
- `wait_for_job_status()` return: record `job_duration`; decrement `active_jobs`; increment `jobs_failed` on non-complete terminal status.

### Log correlation

Inject active `trace_id` and `span_id` into Python `logging` records via a `logging.Filter` so log lines from a training run are linkable to their trace in Grafana/Loki.

### Docs + dashboard

- `docs/source/observability/metrics.rst`
- `docs/observability/grafana-dashboard.json` — sample Grafana dashboard JSON.

**Deliverable**: Full three-pillars observability (traces + metrics + logs).

---

## Phase 5 — Auto-Instrumentation Package  (`v0.5.x`, future)

**Goal**: Zero-code observability. No changes to user scripts required.

Publish `opentelemetry-instrumentation-kubeflow` to PyPI:

- Implements `BaseInstrumentor` from `opentelemetry-instrumentation`.
- Auto-patches `TrainerClient`, `OptimizerClient`, `SparkClient`, `ModelRegistryClient` on import.
- Registers with the `opentelemetry-instrument` CLI entry point.

User experience:

```bash
pip install opentelemetry-instrumentation-kubeflow
opentelemetry-instrument python my_training_script.py
```

**Deliverable**: One-command observability with zero code changes.

---

## Summary

| Phase | SDK version | Scope | Key deliverable |
|---|---|---|---|
| **0** | POC only | Fix POC gaps | Clean reference implementation |
| **1** | `v0.3.x` | Foundation | `opentelemetry-api` dep, `kubeflow/observability/` module |
| **2** | `v0.4.0` | `TrainerClient` | TrainJob traces end-to-end into K8s pods |
| **3** | `v0.4.x` | All clients | Optimizer, Spark, Hub traced; cross-client continuity |
| **4** | `v0.5.0` | Metrics & logs | Operational counters, histograms, log correlation |
| **5** | `v0.5.x` | Auto-instrumentation | `opentelemetry-instrument` CLI integration |

---

*Based on static analysis of `kubeflow-otel-poc/` and `sdk/` at `/Users/ayushpetwal/Desktop/Project 7/`.*
