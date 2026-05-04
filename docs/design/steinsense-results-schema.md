# SteinSense Results Schema

**Date:** 2026-05-03
**Updated:** 2026-05-04 — `seed` renamed to `mc`; batch dispatch OQ added
**Status:** Decision — resolves OQ-4a and OQ-7
**Drives:** R-9 design (Phase 2 item 1), R-6 design (Phase 2 item 2)
**Paper reference:** `implementation-paper-proposal-v7-xla-tpu.md`

---

## Summary of Decisions

| Question | Decision |
|----------|----------|
| OQ-4a: SteinSense single-row or multi-row? | **Single-row.** `run_recovery_*` returns one row per invocation. |
| OQ-4b: EMS R-9 multi-row API contract? | **Open.** Injection code handles both cases identically; validate against Apratim's return structure. |
| OQ-7: git hash per-row or registry record? | **Per-row.** Rationale below. |

---

## OQ-4a Decision: SteinSense Uses Single-Row Output

### What the callable returns

Each `run_recovery_*` invocation returns **one row** in a DataFrame: the aggregate
outcome of one complete recovery attempt. The four output columns are:

| Column | Type | Description |
|--------|------|-------------|
| `wall_time` | float64 | End-to-end seconds, JIT warm-up excluded (amortized over MC replicates when relevant) |
| `n_iterations` | int64 | Iterations to convergence (or `max_iterations` if not converged) |
| `recovered` | bool | True if `final_error < tolerance` at termination |
| `final_error` | float64 | Relative error $\|x^t - x^*\| / \|x^*\|$ at termination |

This matches the paper's stated primary metrics exactly (§Experimental design,
"Primary metrics") and enables the two validation modes the paper requires:

**Aggregate validation** — recovery probability vs. δ curves, convergence iteration
distributions, wall time scaling with (N, B) — all computed from single-row data
via groupby aggregations.

**Instance-level validation** — cross-implementation join on `(N, B, delta, mc)` to
compare `recovered` and `final_error` between implementations — exactly what
BigQuery's table structure supports when all 14 cells share one `table_name`.

### Why not multi-row (iteration trace)?

Multi-row output — one row per AMP iteration, carrying intermediate error, residual
norm, and wall time at each step — would enable more granular convergence analysis.
This was considered and rejected for the primary callable for the following reasons:

1. **Volume.** The full sweep has approximately:
   - Block 1: 5 × 5 × 4 × 3 × 20 = 6,000 parameter combinations
   - Block 2: 2 × 2 × 2 × 1 × 20 = 160 combinations
   - Per cell: ≈ 6,160 invocations
   - 14 cells × 6,160 = 86,240 invocations
   - At up to 50 iterations each: **up to 4.3 million rows** per hardware tier

   Single-row keeps the table at 86K rows per tier — a manageable analytical unit.
   The iteration trace approach inflates it 50×, complicating BigQuery billing and
   query latency.

2. **The paper's RQ1–RQ8 are all answerable from single-row data.** Wall time scaling
   (RQ1), abstraction cost (RQ2), compiler fusion comparison (RQ3), Jacobian speedup
   (RQ4), phase transition fidelity (RQ5), hardware generation (RQ6) all reduce to
   comparisons of `(wall_time, n_iterations, recovered, final_error)` across the
   implementation and hardware axes. No research question in the paper proposal
   requires per-iteration traces to answer.

3. **Instance-level validation is a row-level join, not an iteration-level join.** The
   paper's controlled RNG design enables comparison of `recovered` between
   implementations at the same `(N, B, delta, seed)`. This is a join on single-row
   data; per-iteration traces are not needed.

4. **If iteration traces are needed, they are a separate callable.** A future
   `run_recovery_trace` variant could return a multi-row trace without changing the
   primary callable interface. EMS's R-9 parameter injection works on both; the
   BigQuery table receives it as a distinct `table_name` (e.g.,
   `steinsense_trace_v1`). This extension does not require redesigning the R-9
   contract.

**The SteinSense primary callable is single-row. OQ-4a is resolved.**

Note: multi-row output is a first-class EMS R-9 requirement driven by Apratim Dey's
research code (one row per AMP iteration). SteinSense is the single-row validation
case for R-9; Apratim's pattern is the multi-row case. EMS R-9 must handle both.
The API contract for multi-row is tracked as OQ-4b in `open-questions.md`.

---

## Full Result Row Schema

A complete result row carries three groups of columns.

### Group 1 — Output columns (returned by the callable)

| Column | Type | Notes |
|--------|------|-------|
| `wall_time` | FLOAT64 | Seconds |
| `n_iterations` | INT64 | |
| `recovered` | BOOL | |
| `final_error` | FLOAT64 | |

### Group 2 — Input columns (injected by EMS R-9; manual in EMS v1)

These are injected from `experiment['params']` (swept) and `experiment['fixed_params']`
(fixed). EMS v1 notebooks add them manually; EMS v2 R-9 injects them automatically.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `N` | INT64 | `params` | Signal rows |
| `B` | INT64 | `params` | Signal columns |
| `delta` | FLOAT64 | `params` | Undersampling ratio n/N |
| `distribution` | STRING | `params` | `'normal'`, `'poisson'`, `'binary'` |
| `mc` | INT64 | `params` | MC replicate index (0..19); matches Apratim's BigQuery schema. The callable derives the actual RNG seed internally from `mc` + geometry — `seed_val` is never stored. |
| `implementation` | STRING | `fixed_params` | Backend identifier: `'numpy'`, `'jax_gpu'`, … |
| `jacobian` | STRING | `fixed_params` | `'ad'` or `'closed_form'` |
| `hardware` | STRING | `fixed_params` | `'sherlock_a100'`, `'marlowe_h100'`, `'dgx_spark_gb10'` |
| `max_iterations` | INT64 | `fixed_params` | Convergence cap |
| `tolerance` | FLOAT64 | `fixed_params` | Convergence threshold |

### Group 3 — Provenance columns (injected by EMS R-6; manual in EMS v1)

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `project_git_hash` | STRING | EMS R-6 at launch | 40-char hex SHA of SteinSense repo HEAD |
| `ems_version` | STRING | EMS at launch | EMS package version string |

---

## OQ-7 Decision: Git Hash Per-Row

The git hash of the SteinSense research code belongs **in every result row**, not only
in the experiment registry record.

### Rationale

The SteinSense study runs across months, with bug fixes and algorithm changes occurring
mid-study. The same `table_name` (`steinsense_sweep_v1`) will accumulate results from
multiple code versions:

- v0.1.0 — initial implementation (may have numerical errors discovered later)
- v0.2.0 — bug fix in closed-form Jacobian (per-row masking correction)
- v0.3.0 — float32 precision path added

The paper's correctness claims require knowing which code version produced which rows,
at the row level. Two scenarios illustrate why a registry-only hash is insufficient:

**Scenario A: Partial re-run.** A bug is discovered in the JAX-GPU closed-form
implementation after 3,000 of 6,160 invocations have completed. The fixed version is
committed and the remaining 3,160 are run. The results table now contains rows from
two git hashes at the same `(N, B, delta, mc, implementation, jacobian, hardware)`.
A registry record pointing to one hash misrepresents the true provenance.

**Scenario B: Version comparison.** An analysis notebook queries whether the bug fix
changed the `final_error` distribution. This join requires the hash at the row level.

Per-row storage adds one STRING column per row — negligible cost in BigQuery. The
join to a registry record on every analytical query is a meaningful ergonomic cost.

**Per-row git hash wins on auditability and query ergonomics. OQ-7 is resolved.**

---

## BigQuery Table DDL

The `steinsense_sweep_v1` table DDL, expressed as a BigQuery schema JSON:

```json
[
  {"name": "wall_time",         "type": "FLOAT64",  "mode": "REQUIRED"},
  {"name": "n_iterations",      "type": "INT64",    "mode": "REQUIRED"},
  {"name": "recovered",         "type": "BOOL",     "mode": "REQUIRED"},
  {"name": "final_error",       "type": "FLOAT64",  "mode": "REQUIRED"},

  {"name": "N",                 "type": "INT64",    "mode": "REQUIRED"},
  {"name": "B",                 "type": "INT64",    "mode": "REQUIRED"},
  {"name": "delta",             "type": "FLOAT64",  "mode": "REQUIRED"},
  {"name": "distribution",      "type": "STRING",   "mode": "REQUIRED"},
  {"name": "mc",                "type": "INT64",    "mode": "REQUIRED"},

  {"name": "implementation",    "type": "STRING",   "mode": "REQUIRED"},
  {"name": "jacobian",          "type": "STRING",   "mode": "REQUIRED"},
  {"name": "hardware",          "type": "STRING",   "mode": "REQUIRED"},
  {"name": "max_iterations",    "type": "INT64",    "mode": "REQUIRED"},
  {"name": "tolerance",         "type": "FLOAT64",  "mode": "REQUIRED"},

  {"name": "project_git_hash",  "type": "STRING",   "mode": "REQUIRED"},
  {"name": "ems_version",       "type": "STRING",   "mode": "REQUIRED"}
]
```

### Natural partition and cluster keys

For query performance on the SteinSense analysis workload:

- **Partition by:** `hardware` (analysis almost always scopes to one hardware tier)
- **Cluster by:** `implementation`, `jacobian`, `N` (most groupby/filter patterns)

---

## Impact on R-9 Design

R-9 parameter injection is the same code regardless of how many rows the callable
returns — single-row is just the len=1 case of the general multi-row pattern:

```python
def _inject_params(result: pd.DataFrame, params: dict, fixed_params: dict) -> pd.DataFrame:
    for k, v in {**params, **fixed_params}.items():
        result[k] = v   # pandas broadcasts a scalar to all rows
    return result
```

SteinSense returns one row; Apratim's per-iteration callable returns N rows; both
use the same injection function. No flag, no shape inference, no special casing.
The open design question (OQ-4b) is whether ragged or variable-column DataFrames
create edge cases — validate against Apratim's actual return structure before
closing OQ-4b.

---

## Impact on EMS v1 Compatibility

Until R-9 and R-6 land in EMS v2, the SteinSense notebook adds Groups 2 and 3 manually
in a wrapper at the notebook level (per `steinsense-repo-brief.md`). The callable itself
never sees these columns — it returns Group 1 only. This keeps the callable clean for
the v2 transition: the only change will be removing the wrapper, not touching
`run_recovery_*` functions.

---

## Open Questions Status

| OQ | Status |
|----|--------|
| OQ-4a | **Resolved: single-row.** SteinSense `run_recovery_*` returns one row per invocation. |
| OQ-4b | **Open.** EMS R-9 multi-row API contract — validate against Apratim's return structure. |
| OQ-7 | **Resolved: per-row.** `project_git_hash` in every result row. |
| OQ-12 | **Open.** Batched MC dispatch — `batch_key`/`batch_size` design; dedup grouping; R-9 element-wise injection for batch key. See EMS issue #12. |
