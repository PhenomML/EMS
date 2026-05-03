# EMS Experiment Notebook — Prototype Design v3

**Date:** 2026-05-03
**Status:** Draft
**Base:** [v2](notebook-prototype-v2.md)
**Differs from v2:** Section 3 restructures the experiment dict so that `callable`
encodes the algorithm and implementation directly; `implementation` and `jacobian` move
out of `params` (no longer sweep axes) and into `fixed_params` and the callable name;
`params` is now restricted to pure scientific variables. §Callable Resolution Design
updated with the CELLS pattern for multi-cell studies and the design principle behind
the change. The `fixed_params` convention note corrected accordingly.

---

## Design Principle Added in v3

**The callable name is the primary identifier of what algorithm ran.**

The experiment dict is an artifact of record. Anyone reading it — a collaborator, a
future researcher, an automated registry — should be able to determine the full
experimental intent from the dict alone, without reading the callable's source code.

Concretely: if the point of an experiment is to test JAX-GPU with a closed-form Onsager
Jacobian, that fact belongs in the `callable` field, not buried in a dispatch table
inside `run_recovery`. A generic callable that switches on an `implementation` string
parameter moves the experimental intent into the code and out of the record.

This principle has two consequences:

1. **One callable per algorithm/implementation variant.** Each cell of a multi-cell
   study gets its own callable (and thus its own `callable_file` entry and its own
   experiment dict).
2. **`params` contains only scientific variables.** N, B, δ, seed, distribution — the
   axes that define the problem instance. Implementation choices are not problem
   variables; they belong in `fixed_params`, echoing the callable name for queryability.

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

### Section 3 — Experiment Specification (Code cell) ← changed in v3

The canonical experiment definition. This cell is the science — it must not change
after a run starts.

#### Single-cell experiment (the general case)

```python
experiment = {
    'table_name':    'steinsense_sweep_v1',

    # The callable name IS the algorithm/implementation identifier.
    # Format: 'module.submodule.function_name'
    # Reading this line tells you exactly what ran — no source inspection needed.
    'callable':      'steinsense.jax_gpu.run_recovery_closed',
    'callable_file': 'src/steinsense/jax_gpu.py',

    # Swept parameters — pure scientific variables only.
    # Implementation choices are NOT sweep axes; see fixed_params below.
    'params': [
        # Block 1 — core grid
        {
            'N':            [100, 500, 1000, 2000, 5000],
            'B':            [1, 5, 10, 20, 50],
            'delta':        [0.1, 0.2, 0.3, 0.5],
            'distribution': ['normal', 'poisson', 'binary'],
            'seed':         list(range(20)),
        },
        # Block 2 — large-N extension; restricted (B, δ, distribution)
        {
            'N':            [20_000, 100_000],
            'B':            [10, 50],
            'delta':        [0.2, 0.5],
            'distribution': ['normal'],
            'seed':         list(range(20)),
        },
    ],

    # Fixed parameters — same for every call; injected into every result row.
    # 'implementation' and 'jacobian' mirror the callable name so that BigQuery
    # queries can filter and join without parsing callable strings.
    'fixed_params': {
        'implementation':  'jax_gpu',
        'jacobian':        'closed_form',
        'hardware':        'sherlock_a100',
        'max_iterations':  50,
        'tolerance':       1e-4,
    },
}
```

#### Multi-cell study (the SteinSense 14-cell matrix)

When an experiment covers multiple algorithm/implementation variants, each cell gets
its own dict. The dicts share `table_name` so results accumulate in one BigQuery table
and cross-implementation joins on `(N, B, delta, seed)` are straightforward.

The full matrix is expressed as a list generated from a `CELLS` registry:

```python
# CELLS: one entry per algorithm/implementation variant.
# (callable_name, callable_file, implementation_label, jacobian_label)
CELLS = [
    ('steinsense.numpy.run_recovery_ad',             'numpy.py',    'numpy',       'ad'),
    ('steinsense.numpy.run_recovery_closed',          'numpy.py',    'numpy',       'closed_form'),
    ('steinsense.jax_cpu.run_recovery_ad',            'jax_cpu.py',  'jax_cpu',     'ad'),
    ('steinsense.jax_cpu.run_recovery_closed',        'jax_cpu.py',  'jax_cpu',     'closed_form'),
    ('steinsense.jax_gpu.run_recovery_ad',            'jax_gpu.py',  'jax_gpu',     'ad'),
    ('steinsense.jax_gpu.run_recovery_closed',        'jax_gpu.py',  'jax_gpu',     'closed_form'),
    ('steinsense.pytorch_gpu.run_recovery_ad',        'pytorch_gpu.py', 'pytorch_gpu', 'ad'),
    ('steinsense.pytorch_gpu.run_recovery_closed',    'pytorch_gpu.py', 'pytorch_gpu', 'closed_form'),
    ('steinsense.cupy.run_recovery_ad',               'cupy.py',     'cupy',        'ad'),
    ('steinsense.cupy.run_recovery_closed',           'cupy.py',     'cupy',        'closed_form'),
    ('steinsense.triton.run_recovery_ad',             'triton.py',   'triton',      'ad'),
    ('steinsense.triton.run_recovery_closed',         'triton.py',   'triton',      'closed_form'),
    ('steinsense.cutile.run_recovery_ad',             'cutile.py',   'cutile',      'ad'),
    ('steinsense.cutile.run_recovery_closed',         'cutile.py',   'cutile',      'closed_form'),
]

CORE_PARAMS = [
    {
        'N':            [100, 500, 1000, 2000, 5000],
        'B':            [1, 5, 10, 20, 50],
        'delta':        [0.1, 0.2, 0.3, 0.5],
        'distribution': ['normal', 'poisson', 'binary'],
        'seed':         list(range(20)),
    },
    {
        'N':            [20_000, 100_000],
        'B':            [10, 50],
        'delta':        [0.2, 0.5],
        'distribution': ['normal'],
        'seed':         list(range(20)),
    },
]

experiments = [
    {
        'table_name':    'steinsense_sweep_v1',
        'callable':      callable_name,
        'callable_file': f'src/steinsense/{file}',
        'params':        CORE_PARAMS,
        'fixed_params':  {
            'implementation':  impl,
            'jacobian':        jac,
            'hardware':        'sherlock_a100',
            'max_iterations':  50,
            'tolerance':       1e-4,
        },
    }
    for callable_name, file, impl, jac in CELLS
]
```

Hardware variants (Marlowe H100, DGX Spark GB10) produce separate `experiments` lists
with the appropriate `CELLS` subset (cuTile excluded from Marlowe) and `hardware` label.
All lists share `table_name = 'steinsense_sweep_v1'`.

---

### Section 4 — Computation Configuration (Code cell)

Cluster setup and storage backend selection. Kept separate from the experiment
specification so that cluster config can change without touching the science.

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

Dispatches the experiment to the cluster. The callable is resolved from the experiment
dict — it is not a separate argument to `do_on_cluster()`.

For a single-cell experiment:

```python
from EMS import do_on_cluster

do_on_cluster(experiment, client, db)
```

For the multi-cell matrix, iterate over the list:

```python
from EMS import do_on_cluster

for experiment in experiments:
    db = Databases(table_name=experiment['table_name'])
    do_on_cluster(experiment, client, db)
```

In Phase 3 (Prefect integration), each experiment in the list becomes a separate
Prefect Flow submission — one per cell, running concurrently on the hub:

```python
# Phase 3 form (not yet available):
# from EMS.flows import submit_experiment
# run_urls = [submit_experiment(exp, cluster_config) for exp in experiments]
# for url in run_urls:
#     print(f'Track at: {url}')
```

---

### Section 5b — Results Recovery (Code cell)

Standard query to load computed results. All cells in a multi-cell study share
`table_name`, so results from every implementation are recovered together.

```python
results = db.read_table(experiment['table_name'])
print(f'{len(results):,} rows recovered')
results.head()
```

For BigQuery — cross-implementation join example:

```python
# import pandas_gbq
# results = pandas_gbq.read_gbq("""
#     SELECT
#         N, B, delta, seed,
#         implementation, jacobian, hardware,
#         wall_time, n_iterations, recovered
#     FROM `my_project.my_dataset.steinsense_sweep_v1`
#     WHERE hardware = 'sherlock_a100'
# """, project_id='my_project')
#
# # Compare AD vs closed_form for JAX-GPU:
# jax = results[results.implementation == 'jax_gpu']
# pivot = jax.pivot_table(index=['N', 'B'], columns='jacobian',
#                          values='wall_time', aggfunc='mean')
```

---

### Section 6 — Progress Heatmap (Code cell)

For a single-cell experiment, the heatmap shows completion across the scientific
parameter grid. For the multi-cell matrix, run one heatmap per experiment dict
(one per implementation × jacobian combination).

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

# For multi-cell: filter completed to this cell's fixed_params
cell_filter = {k: v for k, v in experiment['fixed_params'].items()
               if k in ('implementation', 'jacobian', 'hardware')}
# (requires completed to be a DataFrame, not a set — API extension needed)

expected['_done'] = expected.apply(
    lambda row: tuple(row[k] for k in sorted(row.index)) in completed, axis=1
)

pivot = (expected.groupby([Y_AXIS, X_AXIS])['_done']
                  .mean()
                  .unstack(X_AXIS))

fig, ax = plt.subplots(figsize=(8, 5))
sns.heatmap(pivot, annot=True, fmt='.0%', vmin=0, vmax=1,
            cmap='YlGn', linewidths=0.5, ax=ax)
ax.set_title(
    f"{experiment['fixed_params'].get('implementation', '')} / "
    f"{experiment['fixed_params'].get('jacobian', '')} — "
    f"{experiment['table_name']} completion"
)
plt.tight_layout()
plt.show()
```

**Open question (carried from v1):** For grids with more than 2 parameter axes, how
should the researcher select which axes to visualize?
- **Option A (edit-the-cell):** Researcher edits `X_AXIS` / `Y_AXIS` constants.
- **Option B (ipywidgets dropdown):** Interactive dropdowns auto-populated from keys.

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

The callable must be importable from the Dask workers' Python environment.

### The callable name as audit trail

The callable string is the primary provenance record. In the experiment registry,
`'steinsense.jax_gpu.run_recovery_closed'` is unambiguous: JAX-GPU backend,
closed-form Onsager Jacobian. No source inspection required. The `fixed_params`
mirror (`implementation`, `jacobian`) exist solely so BigQuery queries can filter
on plain column values without parsing strings.

### The CELLS pattern

For multi-cell studies the `CELLS` list is the configuration record: it defines
the full experimental matrix in one place. Each generated dict is independently
self-describing; the list is the authoritative statement of which cells are in scope
for the study. Hardware-specific variants (cuTile excluded on Hopper) are expressed
as separate `CELLS` subsets.

### Relationship to R-9 (Parameter Injection)

With `callable` in the dict, EMS owns dispatch end-to-end and knows the full input
to each callable invocation: `{**swept_params, **fixed_params}`. EMS injects these
into every result row before storage. The researcher's callable returns only computed
output values.

```
callable(**{**swept_params, **fixed_params})
  → researcher's DataFrame (output columns only)
  → EMS injects all inputs (swept + fixed)
  → stored row: N, B, delta, seed, implementation, jacobian, hardware,
                max_iterations, tolerance, wall_time, n_iterations, recovered, ...
```

### The `fixed_params` convention

`fixed_params` values do not generate sweep dimensions but appear in every result row.
They fall into two categories:

- **Algorithm identity**: `implementation`, `jacobian` — mirror the callable name;
  always present for queryability.
- **Run context**: `hardware`, `max_iterations`, `tolerance` — operational constants
  that may vary between hardware tiers or study phases.

`params` contains scientific variables only: dimensions of the problem instance
(N, B, δ), the signal distribution, and the RNG seed. If a variable defines the
problem, it belongs in `params`. If it defines the method or context, it belongs
in `fixed_params` or the callable name.

### Serialization

The experiment dict is fully JSON-serializable. `record_experiment()` writes it
as-is; the registry stores it as the canonical record of what ran.

### Open questions

1. **Worker import path**: install, `client.upload_file()`, or shared filesystem?
   Must resolve before Prefect integration design.
2. **Callable verification at launch**: check importability before dispatching?
3. **Backwards compatibility**: migration path for existing call sites that pass
   the callable explicitly to `do_on_cluster()`.
4. **Progress heatmap filtering**: `db.read_params()` currently returns a set of
   tuples. Multi-cell heatmaps need to filter completed rows by `fixed_params`
   values — requires `read_params()` to return a DataFrame or accept a filter.

---

## Prototype Variants

| ID | Name | Cluster | Storage | Purpose |
|----|------|---------|---------|---------|
| NB-A | `prototype_local.ipynb` | `LocalCluster` | SQLite | Baseline; no credentials |
| NB-B | `prototype_remote.ipynb` | Sherlock / DGX | BigQuery | Production pattern |
| NB-C | `prototype_prefect.ipynb` | Prefect flow | BigQuery | Fire-and-forget (Phase 3) |

---

## What Requires New EMS Code

| Feature | Current state | Work needed |
|---------|---------------|-------------|
| `callable` in dict | Not supported | `_resolve_callable()`; `do_on_cluster()` refactor |
| `fixed_params` in dict | Not supported | Merge with swept params before dispatch; inject into results |
| Parameter injection (R-9) | Not implemented | Inject `{**swept, **fixed}` into every result row |
| `read_params()` filtering | Returns set of tuples | Extend to return DataFrame or accept filter kwargs |
| Environment capture (R-6) | Inline subprocess | `EMS.capture_environment()` |
| Fire-and-forget launch | Blocking call | Phase 2 item 4: Prefect integration |
| `unroll_experiment()` public | Internal function | Confirm public export in package refactor |

---

## Open Questions

1. **Worker import path**: install, `upload_file()`, or shared filesystem?
2. **Callable verification at launch**: check importability before dispatching?
3. **Backwards compatibility**: migration path for existing `do_on_cluster()` callers.
4. **`read_params()` API extension**: needs filtering for multi-cell heatmaps.
5. **Heatmap axis selection for N>2 parameters**: edit-the-cell vs. ipywidgets.
   (Carried from v1.)
6. **Section 5a / 5b split**: single cell vs. two cells. (Carried from v1.)
