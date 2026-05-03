# SteinSense Repo — Creation Brief

**Date:** 2026-05-03
**Author:** EMS design session (Claude Sonnet 4.6 + Andrew Donoho)
**For:** SteinSense Claude instance bootstrapping the SteinSense repository
**EMS design baseline:** `notebook-prototype-v3.md`, `phase2-plan.md` (2026-05-03)

---

## Purpose

This document briefs the Claude instance creating the SteinSense repository on the
conventions and design decisions established in the EMS Phase 2 design process. The
SteinSense study is the **primary validation challenge** for EMS Phase 2 — it drives
every major EMS design decision. The two repos must stay in phase: as EMS design
advances, the SteinSense repo updates to use new features.

Read these EMS documents before starting:
- `docs/design/implementation-paper-proposal-v7-xla-tpu.md` — the paper spec
- `docs/design/notebook-prototype-v3.md` — the notebook and experiment dict design
- `docs/design/phase2-plan.md` — the overall EMS Phase 2 architecture

---

## Repo Identity

```
Remote:  git@adonoho-GitHub:PhenomML/SteinSense.git
Branch:  main (development on feature branches as needed)
```

---

## Directory Structure

```
SteinSense/
  src/steinsense/
    __init__.py
    numpy.py            ← CPU reference; run_recovery_ad, run_recovery_closed
    jax_cpu.py          ← JAX on CPU; run_recovery_ad, run_recovery_closed
    jax_gpu.py          ← JAX on GPU; run_recovery_ad, run_recovery_closed
    pytorch_gpu.py      ← PyTorch on GPU; run_recovery_ad, run_recovery_closed
    cupy.py             ← cuPy/cuBLAS; run_recovery_ad, run_recovery_closed
    triton.py           ← Triton kernels; run_recovery_ad, run_recovery_closed
    cutile.py           ← cuTile; run_recovery_ad, run_recovery_closed
  notebooks/
    sherlock_a100/
      steinsense_sweep_v1.ipynb
    marlowe_h100/
      steinsense_sweep_v1.ipynb
    dgx_spark_gb10/
      steinsense_sweep_v1.ipynb
  tests/
    verify_onsager_jacobian_v3.py   ← closed-form Jacobian validation (already written)
  environment.yml                   ← GPU-capable conda env
  pyproject.toml
  CLAUDE.md
```

---

## Callable Naming Convention

This is the central design decision from EMS `notebook-prototype-v3.md`. **The callable
name is the primary identifier of what algorithm ran.** Reading the callable field in
an experiment dict must tell you exactly what ran without inspecting source code.

Each backend module (`numpy.py`, `jax_gpu.py`, etc.) exposes exactly two public
entry points:

| Function | Jacobian method |
|----------|----------------|
| `run_recovery_ad` | Automatic differentiation (`vmap(jacfwd(...))`) |
| `run_recovery_closed` | Closed-form Onsager Jacobian (proved lemma; see paper §Contributions) |

The EMS experiment dict `callable` field uses the fully-qualified path:

```python
'callable': 'steinsense.jax_gpu.run_recovery_closed'
```

This string is unambiguous: JAX-GPU backend, closed-form Jacobian. No source
inspection, no dispatch table, no string matching inside the callable.

**Do not** create a generic `run_recovery` that dispatches on an `implementation`
string parameter. That moves the experimental intent into code and out of the record.

---

## Callable Interface

Each `run_recovery_*` function accepts all parameters as keyword arguments and returns
a DataFrame of **output columns only**. EMS will inject input parameters into every
result row when R-9 (parameter injection) lands in EMS v2.

```python
import pandas as pd

def run_recovery_closed(
    # Scientific parameters (from experiment dict 'params')
    N: int,
    B: int,
    delta: float,
    distribution: str,
    seed: int,
    # Identity parameters (from experiment dict 'fixed_params')
    implementation: str,
    jacobian: str,
    hardware: str,
    # Algorithm hyperparameters (from experiment dict 'fixed_params')
    max_iterations: int,
    tolerance: float,
    **kwargs,              # absorb any future EMS injections gracefully
) -> pd.DataFrame:
    """
    Returns output columns only. EMS injects input params into every row.
    """
    # ... algorithm ...
    return pd.DataFrame({
        'wall_time':    [wall_time],     # float: seconds, JIT warm-up excluded
        'n_iterations': [n_iters],       # int: iterations to convergence
        'recovered':    [recovered],     # bool: converged within tolerance
        'final_error':  [final_err],     # float: relative error at termination
    })
```

### EMS v1.0 Compatibility Note

EMS v1.0 (current release) does **not** inject parameters into result rows — R-9 has
not yet landed. Until EMS v2 ships R-9, every result row must carry the input params
alongside the output columns. Handle this at the notebook level, not in the callable:

```python
# In the experiment notebook (Section 5a), wrap the callable:
import functools
from EMS import do_on_cluster

def wrapped(experiment):
    """Temporary v1 compat wrapper — remove when EMS R-9 lands."""
    original_callable = resolve_callable(experiment['callable'])
    fixed = experiment.get('fixed_params', {})

    def _fn(**params):
        result = original_callable(**params, **fixed)
        for k, v in {**params, **fixed}.items():
            result[k] = v
        return result

    return _fn
```

This keeps the callable clean for when R-9 lands — the only change needed will be
removing the wrapper, not touching the callable itself.

### The Single-Row vs. Multi-Row Decision (OQ-4)

**Record your decision here and in the SteinSense `CLAUDE.md`.**

The EMS design has an open question (OQ-4 in `docs/design/open-questions.md`) about
whether callables return one row per invocation (single-row) or multiple rows (multi-row,
e.g., one row per AMP iteration).

For SteinSense, the primary metrics (wall_time, n_iterations, recovered, final_error)
suggest **single-row**: one recovery attempt, one result row. However, capturing the
full per-iteration trace (intermediate errors, residuals) is scientifically interesting
and would make this a **multi-row** callable.

Make this decision explicitly before implementing. Record it in `CLAUDE.md`. The EMS
team needs this answer to finalize the R-9 design.

---

## Experiment Dict and Notebook Structure

Follow `notebook-prototype-v3.md` exactly for the six-section notebook structure.

### The CELLS Pattern

The 14-cell implementation matrix is expressed as a `CELLS` list, one entry per
(backend × Jacobian variant) combination. Each cell generates one experiment dict.
All dicts share `table_name` so results from all implementations accumulate in one
BigQuery table and cross-implementation joins on `(N, B, delta, seed)` work without
any special handling.

```python
# In Section 3 of each hardware-tier notebook:

CELLS = [
    # (callable_name,                            file,           impl,         jac)
    ('steinsense.numpy.run_recovery_ad',          'numpy.py',    'numpy',       'ad'),
    ('steinsense.numpy.run_recovery_closed',      'numpy.py',    'numpy',       'closed_form'),
    ('steinsense.jax_cpu.run_recovery_ad',        'jax_cpu.py',  'jax_cpu',     'ad'),
    ('steinsense.jax_cpu.run_recovery_closed',    'jax_cpu.py',  'jax_cpu',     'closed_form'),
    ('steinsense.jax_gpu.run_recovery_ad',        'jax_gpu.py',  'jax_gpu',     'ad'),
    ('steinsense.jax_gpu.run_recovery_closed',    'jax_gpu.py',  'jax_gpu',     'closed_form'),
    ('steinsense.pytorch_gpu.run_recovery_ad',    'pytorch_gpu.py', 'pytorch_gpu', 'ad'),
    ('steinsense.pytorch_gpu.run_recovery_closed','pytorch_gpu.py', 'pytorch_gpu', 'closed_form'),
    ('steinsense.cupy.run_recovery_ad',           'cupy.py',     'cupy',        'ad'),
    ('steinsense.cupy.run_recovery_closed',       'cupy.py',     'cupy',        'closed_form'),
    ('steinsense.triton.run_recovery_ad',         'triton.py',   'triton',      'ad'),
    ('steinsense.triton.run_recovery_closed',     'triton.py',   'triton',      'closed_form'),
    ('steinsense.cutile.run_recovery_ad',         'cutile.py',   'cutile',      'ad'),
    ('steinsense.cutile.run_recovery_closed',     'cutile.py',   'cutile',      'closed_form'),
]
# Note: For Marlowe H100, exclude the two cutile rows — cuTile does not support
# Hopper (cc 9.0). See paper proposal §Hardware matrix for details.

CORE_PARAMS = [
    # Block 1 — core grid
    {
        'N':            [100, 500, 1000, 2000, 5000],
        'B':            [1, 5, 10, 20, 50],
        'delta':        [0.1, 0.2, 0.3, 0.5],
        'distribution': ['normal', 'poisson', 'binary'],
        'seed':         list(range(20)),
    },
    # Block 2 — large-N extension (restricted grid)
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
            'hardware':        'sherlock_a100',   # change per hardware tier
            'max_iterations':  50,
            'tolerance':       1e-4,
        },
    }
    for callable_name, file, impl, jac in CELLS
]
```

---

## CLAUDE.md for the SteinSense Repo

The SteinSense `CLAUDE.md` must record the following so any future Claude instance
picks up the design context:

1. **EMS design baseline**: `notebook-prototype-v3.md` (2026-05-03). When the EMS
   design advances (v4, v5, etc.), update this line and the corresponding notebook
   sections.

2. **Callable convention**: one `.py` file per backend, two entry points each
   (`run_recovery_ad`, `run_recovery_closed`). Callable name encodes the algorithm;
   no internal dispatch on strings.

3. **OQ-4 decision**: single-row or multi-row output — record the decision made here.

4. **EMS v1.0 compat**: the v1 wrapper pattern (above) is temporary. Remove it when
   EMS R-9 lands. Do not bake it into the callables.

5. **Paper reference**: `PhenomML/EMS/docs/design/implementation-paper-proposal-v7-xla-tpu.md`
   is the authoritative spec. Consult it for hardware matrix, parameter sweep values,
   and cuTile availability constraints.

6. **Sync protocol**: when EMS cuts a new design version, the SteinSense repo should
   update its notebooks and wrappers in the same sprint. The two repos are in phase.

---

## Environment

The SteinSense `environment.yml` is separate from the EMS environment. It includes
GPU-specific dependencies that have no place in EMS:

```yaml
name: SteinSense
channels:
  - conda-forge
  - nvidia
dependencies:
  - python=3.11
  - pip
  - numpy
  - pandas
  - pip:
    - jax[cuda12]          # JAX with CUDA 12 support
    - torch                # PyTorch
    - cupy-cuda12x         # cuPy for cuBLAS
    - triton               # OpenAI Triton
    - EMS>=1.0.0           # EMS as a dependency
    # cutile: install per NVIDIA instructions when available
```

EMS is an `environment.yml` dependency of SteinSense, not a submodule.

---

## What to Build First

Implement in this order:

1. **Repo scaffold** — directory structure, `pyproject.toml`, `environment.yml`,
   `CLAUDE.md`, `.gitignore`.

2. **`numpy.py`** — the CPU reference implementation. Both `run_recovery_ad` and
   `run_recovery_closed`. This is the ground truth all other implementations must
   match. Tests in `verify_onsager_jacobian_v3.py` validate the closed-form against
   the AD variant.

3. **`sherlock_a100/steinsense_sweep_v1.ipynb`** — the Sherlock notebook using
   the v3 six-section structure and the CELLS pattern. Implement against the NumPy
   callable only initially; add GPU callables as they are implemented.

4. **GPU backends** — in order of increasing complexity: `jax_cpu.py`, `jax_gpu.py`,
   `pytorch_gpu.py`, `cupy.py`, `triton.py`, `cutile.py`.

5. **Remaining notebooks** — `marlowe_h100/` and `dgx_spark_gb10/` once the
   corresponding hardware is accessible.
