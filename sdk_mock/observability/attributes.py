"""Typed attribute-key constants for Kubeflow spans and metric dimensions.

Organized by domain so it's clear which constant belongs to which part of the
system. Typed constants prevent silent typos and enable IDE autocomplete.

Naming rules:
- Reuse OTel semantic convention names verbatim when one exists (e.g. k8s.namespace.name).
- Use the kubeflow.* namespace for anything Kubeflow-specific.
- Keep metric dimensions low-cardinality — job names / runtime names go on spans only.
"""

# ── Job lifecycle ──────────────────────────────────────────────────────────────
JOB_NAME   = "kubeflow.job.name"    # TrainJob CR name, e.g. "train-a3f8b2c1"
JOB_STATUS = "kubeflow.job.status"  # e.g. "Running", "Complete", "Failed"

# ── Trainer / runtime ─────────────────────────────────────────────────────────
TRAINER_KIND = "kubeflow.trainer.kind"   # CustomTrainer | BuiltinTrainer | CustomTrainerContainer
RUNTIME_NAME = "kubeflow.runtime.name"  # e.g. "torch-distributed", "deepspeed"
NODE_COUNT   = "kubeflow.num_nodes"     # int: requested worker replicas

# ── Backend ────────────────────────────────────────────────────────────────────
BACKEND_KIND  = "kubeflow.backend.kind" 
CONTAINER_RT  = "kubeflow.container.runtime"
NAMESPACE     = "k8s.namespace.name"          # OTel K8s semconv — reused as-is

# ── Model initializer ─────────────────────────────────────────────────────────
# Use gen_ai.request.model ONLY when the SDK references a model by URI
# (e.g. hf://meta-llama/Llama-3). Do NOT set gen_ai.usage.input_tokens or
# gen_ai.usage.output_tokens — those are inference metrics, not training metrics.
MODEL_NAME = "gen_ai.request.model"

# ── Operational — metric dimensions (must stay low-cardinality) ───────────────
OPERATION  = "kubeflow.operation"  # train | get_job | wait_for_job …
ERROR_KIND = "error.type"          # exception class name, e.g. "TimeoutError"
