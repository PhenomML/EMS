# US-005: Standard Researcher — Multi-Phase Experimental Pipeline (Milad)

## Source

Review of MatrixCompletion, Matrix_Denoising, and MiladB90 projects
(/Users/awd/Projects/PhenomML/), 2026-03-25. Researcher: Milad B.

## Researcher Profile

A standard lab researcher running multi-phase experiments across Coiled (GCP) and
Stanford Sherlock (SLURM). Less aggressive than a power user but more representative
of typical lab usage. Kept analysis in a separate Colab notebook (MiladB90). Used
Google Drive and BigQuery as the analysis substrate.

Three projects:
- **MatrixCompletion** — 227 commits, 30+ experiment branches, large parameter sweeps
- **Matrix_Denoising** — 101 commits, 8 branches, consumes MatrixCompletion outputs
- **MiladB90** — Separate repo, 247-cell Colab notebook for cross-experiment analysis

## Story

As a researcher running a multi-phase experiment pipeline where later experiments depend
on results from earlier ones, I want EMS to support the full workflow — from defining
and running phase 1, through extracting derived parameters, to running phase 2 and
analyzing results across all phases — without resorting to manual CSV hand-offs,
duplicated utility scripts, or disconnected notebooks.

## What Worked Well

- Core dispatch and storage (SQLite + BigQuery) worked reliably across both projects.
- Coiled and SLURM integration required minimal code changes.
- BigQuery as the shared substrate allowed cross-project analysis in the Colab notebook.

## Pain Points Observed

### 1. Multi-phase pipeline requires manual CSV hand-off (R-10 gap)
MatrixCompletion results are extracted to `tune_milad_cs_0001.csv` (951 rows of tuned
hyperparameters), then manually fed into Matrix_Denoising via a custom `dict_from_csv()`
function. This is fragile, error-prone, and requires manual column renaming:

```python
# Matrix_Denoising/experiment.py
def dict_from_csv(add: str, rename_cols=None, drop_cols=None, mc_range=(11, 20)) -> list:
    # Reads CSV, renames "nsspecfit_slope" → "noise_scale", drops r2
    # Returns multi_res list for EMS
```

EMS has no native concept of "run experiment A, then use its results as parameters
for experiment B." This is the most significant missing capability for multi-phase
research workflows.
→ **Sharpens R-10: the real pattern is structured parameter extraction from upstream
results, not just ad-hoc DB queries.**

### 2. Duplicate utility scripts across every project
`stack_results.py`, `copy_results_to_cloud.py`, and `write_to_gbq.py` are byte-for-byte
identical in MatrixCompletion and Matrix_Denoising. Every new project requires copying
them. These belong in EMS as first-class utilities:
- `stack_results`: groupby aggregation + CSV export of result tables
- `copy_results_to_cloud`: SQLite → PostgreSQL sync
- `write_to_gbq`: SQLite → BigQuery push

### 3. Variable-length output requires manual shape normalization
When the callable returns variable-length arrays (e.g., singular values whose count
depends on matrix dimensions), the researcher must manually compute the maximum output
size and pad all results to a fixed width:

```python
# MatrixCompletion/experiment.py
max_matrix_dim = 0
for params in mr:
    paramlist = [max_matrix_dim]
    paramlist.extend(params['m'])
    paramlist.extend(params['n'])
    max_matrix_dim = max(paramlist)
for params in mr:
    params['max_matrix_dim'] = [int(max_matrix_dim)]
```

EMS provides no help for callables with variable-length outputs.

### 4. Analysis notebook exists but is completely disconnected
The researcher did keep an analysis notebook — but it lives in a separate repository
(MiladB90), authenticates to Google Colab separately, manually loads data from BigQuery
with hardcoded table names, and has no programmatic link to the experiment code.
The 247-cell notebook is sophisticated (t-tests, FacetGrid plots, cross-experiment
comparison) but its connection to the experiments it analyzes is entirely manual.
→ **Confirms US-003: scaffolding must co-locate the notebook with the experiment and
pre-populate the database connection.**

### 5. Git branches as experiment versions
30+ branches named `milad_mc_0012` through `milad_mc_0038`, each a variant of
`experiment.py` with different parameter grids. No experiment registry means git
branching becomes the versioning mechanism.
→ **Confirms experiment registry requirement (open question 1).**

### 6. Solver failures not surfaced by EMS
MatrixCompletion has 8 commits debugging convex solver (cvxpy) instability. EMS silently
drops failed futures, giving the researcher no systematic view of which parameter
combinations failed or why.
→ **Confirms open question 2 (failure handling).**

## New Requirements Surfaced

### R-10 (sharpened): Structured Experiment Dependencies
R-10 currently says "downstream experiment queries upstream result table." The real
pattern is more structured:
1. Run experiment A across a parameter grid.
2. For each result row, compute derived parameters (e.g., fit a model, extract coefficients).
3. Use those derived parameters as the input grid for experiment B.

EMS should provide a native `derive_params()` pattern: given an upstream table and a
transformation function, produce a parameter list for a downstream experiment — replacing
the CSV hand-off workaround.

### R-11: Common Result Utilities
EMS should provide first-class utilities for:
- Groupby aggregation of result tables (mean, std across Monte Carlo replicates)
- Syncing local SQLite results to remote PostgreSQL or BigQuery
- Exporting result subsets to CSV

These are currently copy-pasted into every project.

### R-12: Variable-Length Output Support
EMS should provide a convention or helper for callables that return variable-length
arrays, so researchers are not responsible for computing max dimensions and padding
results manually.

## Related Requirements

- R-1: Experiment Definition
- R-4: Storage (working well)
- R-9: Parameter injection (not yet implemented; would eliminate manual param merging)
- R-10: Experiment dependencies (sharpened — needs structured derive_params pattern)
- R-11: Common result utilities (new)
- R-12: Variable-length output support (new)
- Open question 1: Experiment registry
- Open question 2: Failure handling
- US-003: Scaffolded analysis notebook
