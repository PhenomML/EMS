# EMS Experiment Notebook — Prototype Design v2

**Date:** 2026-05-03
**Status:** Draft
**Base:** [v1](notebook-prototype-v1.md)
**Differs from v1:** Section 3 adds `callable` field to the experiment dict; Section 5a
removes the callable argument from `do_on_cluster()` (now resolved from the dict);
new §Callable Resolution Design explains the mechanism and its relationship to R-9.

---

## Purpose

Every EMS experiment should be anchored to a single design document that serves two
roles simultaneously:

1. **Specification** — the authoritative record of what was (or will be) run: callable,
   parameter grid, cluster config, code version, storage target.
2. **Record** — a living document that shows progress and links directly to the results.

The document must be highly regular: any lab member picking up a notebook from any
researcher should instantly know where to find the parameter grid, how to re-run the
experiment, and how to load the results. Regularity is enforced by section structure, not
by tooling — every section appears in every notebook, in the same order, with the same
purpose.

---

## Section Structure

### Section 1 — Metadata Header (Markdown cell)

Human-readable label. Fixed fields:

```markdown
# <Experiment Name>

| Field       | Value                  |
|-------------|------------------------|
| Researcher  | <name>                 |
| Project     | <project name>         |
| Date        | <YYYY-MM-DD>           |
| Description | <one-sentence summary> |
```

This cell is never executed. It is the provenance label for the notebook file itself.

---

### Section 2 — Environment Capture (Code cell, auto-runs at open)

Records the exact state of the code at the time the notebook is used. Must capture:

- **EMS version**: `importlib.metadata.version('EMS')`
- **Research project git hash**: `subprocess.check_output(['git', 'rev-parse', 'HEAD'])`
- **Timestamp**: `datetime.now().isoformat()`
- **Conda environment name**: `os.environ.get('CONDA_DEFAULT_ENV')`

Prototype implementation (inline, pre-R-6 landing):

```python
import subprocess, os
from datetime import datetime
import importlib.metadata

env_info = {
    'ems_version':    importlib.metadata.version('EMS'),
    'project_hash':   subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                               text=True).strip(),
    'conda_env':      os.environ.get('CONDA_DEFAULT_ENV', 'unknown'),
    'captured_at':    datetime.now().isoformat(),
}
print(env_info)
```

When R-6 lands, this cell is replaced by a single `EMS.capture_environment()` call.

---

### Section 3 — Experiment Specification (Code cell) ← changed in v2

The canonical experiment definition. This cell is the science — it must not change
after a run starts. If the callable or grid changes, start a new document.

```python
experiment = {
    'table_name': 'my_experiment_v1',

    # NEW in v2: fully-qualified callable name.
    # EMS resolves and invokes this function for each parameter combination.
    # Format: 'module.submodule.function_name'
    'callable': 'steinsense.implementations.run_recovery',

    # Swept parameters — the Cartesian product.
    # Each combo is passed to the callable as **kwargs.
    'params': [
        {
            'N':     [100, 500, 1000],
            'delta': [0.1, 0.2, 0.4],
            'seed':  list(range(20)),
        }
    ],

    # Fixed parameters — same value for every call; not swept.
    # Also passed to the callable as **kwargs, alongside the swept params.
    # NEW in v2: separates swept axes from run-level constants.
    'fixed_params': {
        'max_iterations': 100,
        'tolerance':      1e-4,
    },

    # 'stop_list': [...]  # optional: param combos to skip
}
```

**Why `callable` belongs in the dict:**
The experiment dict is now a fully self-contained, JSON-serializable specification.
It can be stored in the experiment registry, reconstructed from disk, and re-run
without any surrounding Python context beyond `import EMS`. The callable name is
also the primary input to R-9 — EMS knows exactly which parameters were passed to
the callable and can inject them into every result row automatically.

**Why `fixed_params` is separate from `params`:**
Fixed parameters do not generate additional sweep dimensions but are still passed
to the callable and must appear in the result rows. Keeping them separate makes the
Cartesian product grid explicit and prevents single-element lists from cluttering `params`.

The `table_name` declared here is the single source of truth used by Section 5
(launch) and Section 5b (recovery query).

---

### Section 4 — Computation Configuration (Code cell)

Cluster setup and storage backend selection. Kept separate from the experiment
specification so that cluster config (local vs. SLURM vs. cloud) can change without
touching the science.

```python
from dask.distributed import Client, LocalCluster

# --- Choose one cluster configuration ---

# Option A: Local (laptop / workstation)
cluster = LocalCluster(n_workers=4, threads_per_worker=1)
client = Client(cluster)

# Option B: SLURM (Stanford Sherlock)
# from dask_jobqueue import SLURMCluster
# cluster = SLURMCluster(cores=1, memory='4GB', job_extra=['--partition=owners'])
# cluster.scale(jobs=20)
# client = Client(cluster)

# Option C: Coiled (GCP)
# import coiled
# cluster = coiled.Cluster(n_workers=50, region='us-central1')
# client = Client(cluster)

print(client.dashboard_link)

# --- Storage backend ---
from EMS import Databases
db = Databases(table_name=experiment['table_name'])  # SQLite default
# db = Databases(table_name=experiment['table_name'], use_bigquery=True)
```

---

### Section 5a — Launch (Code cell) ← changed in v2

Dispatches the experiment to the cluster. In v2, the callable is resolved from the
experiment dict — it is no longer a separate argument to `do_on_cluster()`.

```python
from EMS import do_on_cluster

# Callable resolved from experiment['callable']; no explicit function argument.
do_on_cluster(experiment, client, db)
```

EMS resolves `experiment['callable']` via `importlib.import_module` at dispatch time,
imports the module, and retrieves the function. If the callable cannot be resolved, EMS
raises `ImportError` before any work is dispatched.

In Phase 3 (Prefect integration), this cell becomes a Prefect flow submission:

```python
# Phase 3 form (not yet available):
# from EMS.flows import submit_experiment
# run_url = submit_experiment(experiment, cluster_config)
# print(f'Track at: {run_url}')
```

Note that in the Phase 3 form the callable is also resolved from the dict on the Prefect
server — the researcher's local Python environment does not need to import the callable.

---

### Section 5b — Results Recovery (Code cell)

Standard query to load computed results back into a DataFrame. The table name comes from
`experiment['table_name']` — no duplication.

```python
results = db.read_table(experiment['table_name'])
print(f'{len(results):,} rows recovered')
results.head()
```

For BigQuery (read-only analysis session, no cluster needed):

```python
# import pandas_gbq
# results = pandas_gbq.read_gbq(
#     f"SELECT * FROM `my_project.my_dataset.{experiment['table_name']}` LIMIT 10000",
#     project_id='my_project',
# )
```

---

### Section 6 — Progress Heatmap (Code cell)

Compares the full expected parameter grid against what has been computed. Requires:
- `unroll_experiment(experiment)` → all expected parameter combos
- `db.read_params(experiment['table_name'])` → already-computed combos

The completion matrix is a 2D boolean grid over two chosen parameter axes, with all
other axes marginalized (a cell is "done" if **all** combos holding the other axes fixed
are complete).

```python
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from EMS import unroll_experiment

# --- Axis selection ---
# Edit these to choose which two parameters define the heatmap axes.
X_AXIS = 'delta'
Y_AXIS = 'N'

expected  = pd.DataFrame(unroll_experiment(experiment))
completed = db.read_params(experiment['table_name'])

# Mark completion
expected['_done'] = expected.apply(
    lambda row: tuple(row[k] for k in sorted(row.index)) in completed, axis=1
)

# Pivot: fraction of replicates done per (X_AXIS, Y_AXIS) cell
pivot = (expected.groupby([Y_AXIS, X_AXIS])['_done']
                  .mean()
                  .unstack(X_AXIS))

fig, ax = plt.subplots(figsize=(8, 5))
sns.heatmap(pivot, annot=True, fmt='.0%', vmin=0, vmax=1,
            cmap='YlGn', linewidths=0.5, ax=ax)
ax.set_title(f"{experiment['table_name']} — completion ({len(completed)} / {len(expected)} rows)")
plt.tight_layout()
plt.show()
```

**Open question (carried from v1):** For grids with more than 2 parameter axes, how
should the researcher select which axes to visualize?
- **Option A (edit-the-cell):** Researcher edits `X_AXIS` / `Y_AXIS` constants. Simple,
  no new dependencies, consistent with the "highly regular" goal.
- **Option B (ipywidgets dropdown):** Interactive dropdowns auto-populated from the
  parameter keys. More usable but adds `ipywidgets` dependency and requires a running
  kernel for the widget to render.

---

## Callable Resolution Design

### The mechanism

When `do_on_cluster(experiment, client, db)` is called, EMS resolves the callable as:

```python
import importlib

def _resolve_callable(name: str):
    module_path, fn_name = name.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, fn_name)
```

The callable must be importable from the Dask workers' Python environment. For SLURM
clusters, this means the research project code must be installed or on `sys.path` on
every worker node.

### Relationship to R-9 (Parameter Injection)

Putting the callable in the dict enables automatic parameter injection. Because EMS
now owns the dispatch loop and knows the full parameter dict passed to each callable
invocation, it can inject those parameters into every result row before storage:

```
callable(**{**swept_params, **fixed_params})
  → researcher's DataFrame (output columns only)
  → EMS injects input params
  → stored row: input params + output columns
```

The researcher's callable returns only computed output values. EMS associates every
result row with its inputs. The `fixed_params` field is also injected — every result
row carries the full call context.

This is the core R-9 implementation path. The callable-in-dict design and R-9 are
co-dependent: R-9 is most cleanly implemented once EMS owns dispatch end-to-end.

### The `fixed_params` convention

`fixed_params` values appear in every result row but do not generate sweep dimensions.
They are useful for:
- Algorithm hyperparameters held constant across the study (e.g., `max_iterations`)
- Hardware or implementation labels when those are not themselves swept axes
  (e.g., `hardware='sherlock_a100'` for a single-cluster run)

When `implementation` and `hardware` are swept (as in the SteinSense study), they
belong in `params`, not `fixed_params`.

### Serialization

The experiment dict with `callable` as a string is fully JSON-serializable:

```python
import json
json.dumps(experiment)  # works; no function objects in the dict
```

This makes `record_experiment()` straightforward: write the dict as JSON with no
special handling. The experiment registry stores this JSON as the canonical record.

### Open questions for this design

1. **Worker import path**: How does EMS ensure the callable's module is importable
   on every Dask worker? Options: (a) require researchers to install their project
   package on all workers; (b) EMS ships the source file to workers via
   `client.upload_file()`; (c) require a shared filesystem (NFS / Lustre on Sherlock).
   This must be resolved before the Prefect integration design.

2. **Callable verification**: Should EMS verify at launch time that `experiment['callable']`
   is importable in the current environment, before dispatching any work? A failed import
   on worker nodes hours into a run is a bad failure mode.

3. **Backwards compatibility**: The current `do_on_cluster(experiment, callable_fn, client, db)`
   signature takes the callable explicitly. The v2 design removes that argument. Migration
   path: accept callable as an optional positional arg; if provided, verify it matches
   `experiment['callable']`; if `experiment['callable']` is absent, use the positional arg
   (v1 compat mode). Deprecate the positional form in v2.1.

---

## Prototype Variants

Three concrete notebooks to build, in order:

| ID | Name | Cluster | Storage | Purpose |
|----|------|---------|---------|---------|
| NB-A | `prototype_local.ipynb` | `LocalCluster` | SQLite | Baseline template; no credentials required |
| NB-B | `prototype_remote.ipynb` | Sherlock / DGX | BigQuery | Production pattern |
| NB-C | `prototype_prefect.ipynb` | Prefect flow | BigQuery | Fire-and-forget; Phase 3 disconnect-and-check |

NB-A is the prerequisite for NB-B and NB-C and is fully buildable against the current
v1.0 EMS codebase (with the callable-in-dict extension from this document).

---

## What Requires New EMS Code

| Notebook section | Current state | EMS work needed |
|-----------------|---------------|-----------------|
| `callable` in dict | Not supported | `_resolve_callable()`; `do_on_cluster()` refactor |
| `fixed_params` in dict | Not supported | Merge into param combo before dispatch |
| Parameter injection (R-9) | Not implemented | Inject input params into result rows |
| Environment capture | Inline subprocess calls | R-6: `EMS.capture_environment()` |
| Launch (fire-and-forget) | Blocking `do_on_cluster()` | Phase 2 item 4: Prefect integration |
| Progress heatmap | Needs `unroll_experiment()` as public API | Minor: confirm public export |
| Results recovery | `db.read_table()` works today | None |

---

## Open Questions

1. **Worker import path for callable**: install, `upload_file()`, or shared filesystem?
2. **Callable verification at launch**: check importability before dispatching?
3. **Backwards compatibility**: migration path for existing `do_on_cluster()` call sites.
4. **Heatmap axis selection for N>2 parameters**: edit-the-cell (Option A) or
   `ipywidgets` dropdowns (Option B)? (Carried from v1.)
5. **Section 5a / 5b split**: single cell (simpler) or two cells (cleaner separation)?
   (Carried from v1.)
