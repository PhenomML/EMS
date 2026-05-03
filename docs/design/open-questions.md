# EMS Design — Open Questions

**Updated:** 2026-05-03 — OQ-4 split into OQ-4a (resolved) and OQ-4b (open); OQ-7 resolved
**Purpose:** Single living document for all unresolved design questions across EMS
Phase 2. Update status here when a question is resolved; do not remove resolved entries
(mark them Resolved with the decision and date). Source documents retain their original
text; this file is the canonical status tracker.

---

## Status Summary

| ID | Question | Status | Blocks |
|----|----------|--------|--------|
| OQ-1 | Worker import path for callable | Open | Prefect integration (item 4) |
| OQ-2 | Callable verification at launch | Open | `do_on_cluster()` refactor |
| OQ-3 | Backwards compatibility for `do_on_cluster()` callers | Open | package refactor (item 0) |
| OQ-4a | SteinSense callable output: single-row or multi-row? | **Resolved** | R-9 design (item 1) |
| OQ-4b | EMS R-9: API contract for multi-row callables | Open | R-9 design (item 1) |
| OQ-5 | `read_params()` filtering for multi-cell heatmaps | Open | progress heatmap usability |
| OQ-6 | Experiment registry implementation | Open | hub/Prefect work (item 4) |
| OQ-7 | Git hash location: per-row vs. registry record | **Resolved** | R-6 (item 2), registry (item 3) |
| OQ-8 | Progress heatmap axis selection for N>2 params | Open | notebook prototype finalization |
| OQ-9 | Section 5a/5b split: one cell or two? | Open | notebook prototype finalization |
| OQ-10 | Failure handling default behavior | Open | hub/Prefect work (item 4) |
| OQ-11 | Cost tracking per experiment | Open | registry design (item 3) |

---

## Callable & Dispatch

### OQ-1 — Worker import path for callable
**Status:** Open
**Raised in:** `notebook-prototype-v2.md`
**Blocks:** Prefect integration (Phase 2 item 4)

When `experiment['callable']` is a fully-qualified module path, that module must be
importable on every Dask worker at dispatch time. Three options:

| Option | Mechanism | Tradeoff |
|--------|-----------|----------|
| A — Install | Researcher installs project package on all worker nodes | Clean; requires package discipline; works for SLURM shared-filesystem clusters |
| B — Upload | EMS calls `client.upload_file(experiment['callable_file'])` before dispatch | Zero-install; `callable_file` field required; may not survive node restart |
| C — Shared filesystem | Rely on NFS/Lustre; add project root to `sys.path` | Works on Sherlock (Lustre); not portable to cloud or DGX Spark |

**Note:** Options are not mutually exclusive. EMS could attempt B automatically when
`callable_file` is present, fall back to A otherwise.

---

### OQ-2 — Callable verification at launch
**Status:** Open
**Raised in:** `notebook-prototype-v2.md`
**Blocks:** `do_on_cluster()` refactor

Should EMS verify that `experiment['callable']` is importable in the current environment
before dispatching any work? A failed import discovered hours into a long run is a bad
failure mode.

**Options:**
- Verify on the dispatch node only (fast; does not catch worker-node import failures)
- Verify on one worker via a test task (slow startup; catches worker failures)
- No verification; fail fast on first worker error (current behavior)

---

### OQ-3 — Backwards compatibility for `do_on_cluster()` callers
**Status:** Open
**Raised in:** `notebook-prototype-v2.md`
**Blocks:** package refactor (Phase 2 item 0)

The v1 signature is `do_on_cluster(experiment, callable_fn, client, db)`. The v2+
design moves the callable into the dict, making the positional argument redundant.

**Proposed migration path:**
- If `experiment['callable']` is present: use it; ignore positional callable if provided
  (with a deprecation warning if both are given).
- If `experiment['callable']` is absent and a positional callable is provided: use it
  (v1 compat mode); emit a deprecation warning.
- Remove positional callable in v2.1.

---

### OQ-4a — SteinSense callable output: single-row or multi-row?
**Status:** Resolved 2026-05-03 — **single-row**. See `steinsense-results-schema.md`.
**Raised in:** `phase2-plan.md`
**Blocks:** R-9 design (Phase 2 item 1)

The `run_recovery_*` callables return one row per invocation: (wall_time,
n_iterations, recovered, final_error). All eight research questions in the paper
are answerable from per-invocation aggregates; per-iteration traces are not needed
for the primary analysis. See `steinsense-results-schema.md` for the full schema.

---

### OQ-4b — EMS R-9: API contract for multi-row callables
**Status:** Open
**Raised in:** this session (split from OQ-4)
**Blocks:** R-9 design (Phase 2 item 1)

Multi-row callables are a first-class EMS requirement, not a future extension.
Apratim Dey's research code returns one row per AMP iteration (intermediate error,
residual, wall time at each step) — a pattern proven scientifically useful for
diagnosing convergence behavior and attributing failures to specific iterations.

SteinSense uses single-row (OQ-4a resolved), but EMS R-9 must handle both cases.
The open question is the API contract: how does R-9 know whether a callable is
single-row or multi-row, and does injection differ?

**Options:**

| Option | Mechanism | Tradeoff |
|--------|-----------|----------|
| A — Infer from shape | If returned DataFrame has >1 row, inject into all rows | Zero API change; can misfire if a single-row callable returns a 1-row DataFrame |
| B — Dict flag | `experiment['multi_row'] = True`; R-9 injects into every row | Explicit; requires researcher to declare intent; breaks if they forget |
| C — Return-type contract | Callable always returns a DataFrame; R-9 always injects into all rows regardless of count | Simplest; single-row is just multi-row with len=1; no special casing |

**Option C is the likely answer:** injection into all rows is identical code regardless
of DataFrame length. Single-row is just the len=1 case. No flag, no inference — just
`for k, v in params.items(): result[k] = v` applied to whatever the callable returns.

**Decision needed before:** implementing R-9. Option C should be validated against
Apratim's actual return structure to confirm no edge cases (e.g., ragged DataFrames,
columns that vary per row).

---

## EMS API

### OQ-5 — `read_params()` filtering for multi-cell heatmaps
**Status:** Open
**Raised in:** `notebook-prototype-v3.md`
**Blocks:** progress heatmap usability for multi-cell studies

`db.read_params(table_name)` currently returns a set of tuples representing
already-computed parameter combinations across the entire table. When multiple
experiment cells share one `table_name` (as in the SteinSense 14-cell matrix),
the returned set contains completions from all implementations mixed together.

A per-cell heatmap needs to filter completed rows to a specific `(implementation,
jacobian, hardware)` combination.

**Options:**
- Extend `read_params()` to accept a `filter` dict: `read_params(table_name, filter={'implementation': 'jax_gpu', 'jacobian': 'closed_form'})`
- Return a DataFrame instead of a set, letting callers filter with pandas
- Add a separate `read_params_filtered()` method

---

## Experiment Registry

### OQ-6 — Experiment registry implementation
**Status:** Open
**Raised in:** `docs/VISION.md` (Open Question 1), `phase2-plan.md`
**Blocks:** hub/Prefect work (Phase 2 item 4)

The registry must be queryable by researcher, project, date, code version (git hash),
and must link to the experiment design document. The SteinSense study adds: must also
track which callable (implementation × jacobian) ran on which hardware.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| BigQuery table | Same query tool as results; multi-researcher; durable | Requires BigQuery credentials at launch; cloud dependency |
| Structured JSON directory | Zero dependencies; git-trackable; human-readable | Not queryable across machines without a query layer; grows without bound |
| Prefect Flow metadata | Free if Prefect is already running; UI search | Requires Prefect running; not queryable via SQL; loses history if Prefect DB is reset |

**Evidence from researchers:** Apratim Dey used 70+ git branches as a substitute;
Milad B used 30+. Both confirm the need is real and the absence is painful.

**Note:** The experiment dict (v3 design) is already JSON-serializable. The JSON
directory option is the lowest-friction starting point — the dict is the registry
entry. A BigQuery table can be added later without changing the dict format.

---

### OQ-7 — Git hash location: per-row vs. registry record
**Status:** Resolved 2026-05-03 — **per-row**. See `steinsense-results-schema.md`.
**Raised in:** `phase2-plan.md`
**Blocks:** R-6 (Phase 2 item 2), registry design (item 3)

The research project git hash (R-6) can live in two places:

- **Per result row**: every row in the results table carries `project_git_hash`.
  Allows per-row provenance; handles the case where results from multiple code
  versions accumulate in one table. More storage; heavier write path.
- **Registry record only**: the hash is stored once in the experiment registry
  record, not in every row. Lighter; requires a join to the registry to get
  provenance. Works cleanly when one experiment = one code version (the normal case).

**SteinSense context:** the paper's correctness claims require knowing which git hash
produced which results. If results from two code versions can coexist in one table
(e.g., after a bug fix mid-run), per-row is safer. If a new run always uses a new
`table_name`, registry-level is sufficient.

---

## Visualization

### OQ-8 — Progress heatmap axis selection for N>2 parameters
**Status:** Open
**Raised in:** `notebook-prototype-v1.md`
**Blocks:** notebook prototype finalization

When the parameter grid has more than 2 axes, the researcher must choose which two
to display on the heatmap. All other axes are marginalized (a cell is "done" if all
combos with the other axes fixed are complete).

**Options:**
- **Option A (edit-the-cell):** Researcher edits `X_AXIS` / `Y_AXIS` constants in the
  notebook cell. Simple; no new dependencies; consistent with the "highly regular" goal.
- **Option B (ipywidgets dropdown):** Interactive dropdowns auto-populated from the
  parameter keys. More usable; adds `ipywidgets` dependency; requires live kernel.

**Leaning toward Option A** on grounds of simplicity and regularity. Option B can
be a later addition if researchers request it.

---

### OQ-9 — Section 5a/5b split: one cell or two?
**Status:** Open
**Raised in:** `notebook-prototype-v1.md`
**Blocks:** notebook prototype finalization

Should the launch (write path) and results recovery (read path) be one notebook cell
or two?

- **One cell:** simpler; researcher runs one cell to launch and immediately sees results.
  Conflates write and read paths; harder to re-run results recovery without re-launching.
- **Two cells:** cleaner separation; researcher can re-run Section 5b independently
  to reload results without re-launching the experiment. Preferred for multi-hour runs.

**Leaning toward two cells** given that SteinSense runs take significant time and
result recovery is a frequent operation during analysis.

---

## Infrastructure & Operations

### OQ-10 — Failure handling default behavior
**Status:** Open
**Raised in:** `docs/VISION.md` (Open Question 2), `phase2-plan.md`
**Blocks:** hub/Prefect work (Phase 2 item 4)

Both Apratim Dey and Milad B experienced silent failure drops with no post-mortem
data available. Current behavior: failed Dask futures are logged as warnings and
skipped.

**Questions to resolve:**
1. Should failed instances be re-queued automatically, flagged for manual review,
   or logged and skipped (current behavior)?
2. Should there be a per-experiment default that researchers can override?
3. What post-mortem data should be captured — parameters, exception type, traceback,
   worker identity?

**Prefect context:** Prefect supports retry policies at the Flow and Task level.
The retry question may be partially answered by the Prefect integration design.

---

### OQ-11 — Cost tracking per experiment
**Status:** Open
**Raised in:** `docs/VISION.md` (Open Question 3), `docs/EMS_Model.md`
**Blocks:** registry design (Phase 2 item 3)

Should EMS record cloud compute cost per experiment and report against funding accounts?
`docs/EMS_Model.md` specifies a `Funding` table and per-experiment cost attribution.

**Questions:**
- Which cost signals are accessible? (Coiled exposes cost per cluster-hour; SLURM
  may expose CPU-hours via `sacct`; local clusters have no direct cost signal.)
- Is cost tracking a registry field (recorded once per experiment) or a per-row metric?
- Is this required for Phase 2, or deferred to Phase 3?

**Tentative:** Defer to Phase 3. Cost tracking is desirable but not blocking for the
SteinSense study or the core Phase 2 hub features.
