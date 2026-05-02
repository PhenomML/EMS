# EMS Experiment Notebook — Prototype Design v1

**Date:** 2026-04-23
**Status:** Draft — open question on heatmap interaction model (see §6)

---

## Purpose

Every EMS experiment should be anchored to a single Jupyter notebook that serves two
roles simultaneously:

1. **Specification** — the authoritative record of what was (or will be) run: parameter
   grid, cluster config, code version, storage target.
2. **Record** — a living document that shows progress and links directly to the results.

The notebook must be highly regular: any lab member picking up a notebook from any
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

### Section 3 — Experiment Specification (Code cell)

The canonical hyperparameter definition. This cell is the science — it must not change
after a run starts. If the grid changes, a new notebook (or a clearly versioned cell)
should record it.

```python
experiment = {
    'table_name': 'my_experiment_v1',
    'params': [
        {
            'n':        [100, 200, 500, 1000],
            'delta':    [0.1, 0.2, 0.4, 0.8],
            'replicate': list(range(50)),
        }
    ],
    # 'stop_list': [...]  # optional: param combos to skip
}
```

The `table_name` declared here is the single source of truth used by Section 5 (launch)
and Section 5b (recovery query). It must not be repeated or re-declared elsewhere in the
notebook.

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

### Section 5a — Launch (Code cell)

Dispatches the experiment to the cluster. The callable (`my_compute_fn`) is the
researcher's function; EMS owns everything else.

```python
from EMS import do_on_cluster

do_on_cluster(experiment, my_compute_fn, client, db)
```

In Phase 3 (Prefect integration), this cell becomes a Prefect flow submission that
returns immediately, allowing the researcher to disconnect:

```python
# Phase 3 form (not yet available):
# from EMS.flows import submit_experiment
# run_url = submit_experiment(experiment, my_compute_fn, cluster_config)
# print(f'Track at: {run_url}')
```

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
Y_AXIS = 'n'

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

**Open question:** For grids with more than 2 parameter axes, how should the researcher
select which axes to visualize?
- **Option A (edit-the-cell):** Researcher edits `X_AXIS` / `Y_AXIS` constants. Simple,
  no new dependencies, consistent with the "highly regular" goal.
- **Option B (ipywidgets dropdown):** Interactive dropdowns auto-populated from the
  parameter keys. More usable but adds `ipywidgets` dependency and requires a running
  kernel for the widget to render.

---

## Prototype Variants

Three concrete notebooks to build, in order:

| ID   | Name                      | Cluster        | Storage  | Purpose                                       |
| ---- | ------------------------- | -------------- | -------- | --------------------------------------------- |
| NB-A | `prototype_local.ipynb`   | `LocalCluster` | SQLite   | Baseline template; no credentials required    |
| NB-B | `prototype_remote.ipynb`  | Sherlock / DGX | BigQuery | Production pattern                            |
| NB-C | `prototype_prefect.ipynb` | Prefect flow   | BigQuery | Fire-and-forget; Phase 3 disconnect-and-check |

NB-A is the prerequisite for NB-B and NB-C and is fully buildable against the current
v1.0 EMS codebase. NB-B and NB-C require Phase 2 work items 3–4.

---

## What Requires New EMS Code

| Notebook section | Current state | EMS work needed |
|-----------------|---------------|-----------------|
| Environment capture | Inline subprocess calls | R-6: `EMS.capture_environment()` |
| Launch (fire-and-forget) | Blocking `do_on_cluster()` | Phase 2 item 3: Prefect integration |
| Progress heatmap | Needs `unroll_experiment()` exposed as public API | Minor: confirm public export |
| Results recovery | `db.read_table()` works today | None |
| All other sections | Work today | None |

---

## Open Questions

1. **Heatmap axis selection for N>2 parameters**: edit-the-cell (Option A) or
   `ipywidgets` dropdowns (Option B)? See §6.
2. **Notebook storage location**: should prototype notebooks live in `notebooks/` at the
   repo root, or in a researcher project template directory?
3. **Section 5a / 5b split**: should launch and recovery be a single cell (simpler) or
   two cells (cleaner separation of write path vs. read path)?
