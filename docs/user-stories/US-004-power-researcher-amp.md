# US-004: Power Researcher — Large-Scale Algorithm Exploration (AMP)

## Source

Review of AMP_matrix_recovery project (/Users/awd/Projects/MultiverseExperiments/AMP_matrix_recovery),
2026-03-25. Researcher: Apratim Dey (apd1995).

## Researcher Profile

A technically aggressive researcher running large-scale parameter sweeps across SLURM
(Stanford Sherlock) and Coiled (GCP cloud). Produced 14 experiment runner scripts, 70+
git branches, and 116 JSON experiment definition files. Thousands of parameter combinations
computed. No analysis notebooks kept in the project.

## Story

As a power researcher running large-scale embarrassingly parallel experiments across
multiple compute backends, I want EMS to handle dispatch, deduplication, and result
storage so I can focus entirely on algorithm development — and I want the path from
completed run to visible results to require zero manual steps.

## What Worked Well

- `do_on_cluster()` scaled from laptop to 1,500 SLURM workers to 500 Coiled workers
  with no code changes beyond the cluster setup block.
- The same experiment JSON ran across all backends.
- Deduplication and resume worked correctly across large parameter spaces.
- Write batching handled high-throughput result streams without data loss.

## Pain Points Observed

### 1. No analysis notebooks — ever
Zero analysis notebooks exist in the project despite PI urging. The friction of connecting
a notebook to the database was enough to prevent it entirely. Results were computed but
many were never examined.
→ **Addressed by US-003 (scaffolded notebook).**

### 2. Manual parameter injection (R-9 gap)
Every `run_amp_instance()` call manually merges input params into the result:
```python
combined_dict = {**dict_params, **dict_observables}
```
If a parameter is added to the experiment but forgotten in the return dict, it silently
disappears from the database. This happened: `selected_rows_frac` appears in experiment
definitions but not in the function signature.
→ **Addressed by R-9 (EMS injects params at v1.0).**

### 3. JSON files scattered in CWD
`record_experiment()` writes timestamped JSON files to the current working directory.
13 files accumulated in the project root; an `exp_dicts/` subdirectory exists but was
not consistently used. No queryable index of what was run when.
→ **Requires experiment registry (open question 1) and configurable record path.**

### 4. Research code version not captured
`environment.yml` pins `EMS@v0.0.17` but the research code itself (the algorithm scripts)
has no version captured at run time. Git hash capture (R-6) must cover both EMS and the
research project code.

### 5. Multi-row results per instance
`run_amp_instance()` emits one DataFrame row every 50 AMP iterations — not one row per
parameter combination. R-9's parameter injection must handle multi-row returns correctly:
inject input params into every row, not just the first.

### 6. No failure handling
Failed Dask futures are silently skipped. No log of which parameter combinations failed,
no retry, no way to identify what went wrong after the fact.
→ **Addressed by open question 2 (failure handling).**

### 7. Git branches as experiment versions
70+ branches named by experiment (e.g., `apd1995-JS-normal-jit-v3`) because there is
no experiment registry. Git branching is the workaround for versioned experiment
definitions.
→ **Addressed by experiment registry (open question 1).**

## New Requirements Surfaced

- **R-9 multi-row**: Parameter injection must work for callables that return multiple
  rows per invocation, not just single-row results.
- **R-6 scope**: Git hash capture must cover research project code, not only EMS version.
- **Experiment registry**: The 116 JSON files and 70 branches make clear this is not
  optional — it is essential for any project of meaningful scale.

## Related Requirements

- R-1, R-2, R-3, R-4 (all working well at scale)
- R-6: Environment reproducibility (partial — EMS version tracked, research code not)
- R-9: Parameter injection (not yet implemented)
- R-10: Experiment dependencies (single-phase project; not tested)
- Open question 1: Experiment registry
- Open question 2: Failure handling
- US-003: Scaffolded analysis notebook
