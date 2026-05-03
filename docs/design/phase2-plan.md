# EMS Phase 2 — Architecture & Plan

**Date:** 2026-05-03
**Status:** Active — design phase; implementation not yet begun
**Branch:** `claude-v2.0.0_phase2`

---

## Where We Are

EMS v1.0.0 is live on `main` (tagged, pushed 2026-04-25). It is a working library for
embarrassingly parallel scientific computation: define a parameter grid, dispatch to a
Dask cluster, deduplicate against previously computed results, write batched results to
SQLite / PostgreSQL / BigQuery.

What v1.0.0 does not do:
- Persistent job execution (experiments die if the researcher's process dies)
- Git hash or environment capture at run time
- Parameter injection into result rows (researchers must do this manually)
- A structured experiment registry
- A web-visible progress dashboard
- Common result utilities (aggregation, sync, CSV export)

Phase 2 delivers all of these.

---

## The Architecture

### Two-System Design

EMS is two systems separated by BigQuery as the data contract:

**Compute backend** — specifies experiments, dispatches to clusters, writes results.
This is the EMS library. The researcher interacts with it to define parameter spaces
and launch runs.

**Analysis frontend** — a researcher's local Jupyter or R session connected directly
to BigQuery. Queries results, renders visualizations, develops hypotheses. Does not
move data; only reads.

Nothing important lives outside the database. The compute backend writes; the analysis
frontend reads. This separation means the two systems can evolve independently.

### Hub Architecture

Phase 2 adds a hub layer between the researcher and the compute cluster:

```
Researcher (any device, Tailscale)
        │
   ┌────┴──────────────────────┐
   │                           │
   ▼                           ▼
Prefect Server             Dask Dashboard
(job submit / history /    (live cluster view —
 experiment registry)       free while cluster runs)
        │
        │ DaskTaskRunner
        ▼
   Dask Cluster  ──writes──▶  BigQuery / SQLite
   (Sherlock / DGX Spark / Coiled on GCP)
        │
        ▼
   Analysis Notebook  ──reads──▶  BigQuery
   (local Jupyter / R)
```

**Prefect Server** runs as a persistent service on the lab's Intel Mac Pro (Tailscale-
accessible). Researchers submit experiments via Prefect's web UI or Python API and
immediately disconnect. The experiment runs to completion as a server-side Prefect Flow.
Job status, logs, and run history are visible from any device via Tailscale URL.

**Dask** remains the compute engine. Prefect owns the job lifecycle; Dask owns the
parallel dispatch. Each does what it does best. `do_on_cluster()` maps directly onto a
Prefect Flow with a thin wrapper — no change to the existing dispatch logic.

**BigQuery** is the data contract for multi-cluster work. All clusters (Sherlock, Marlowe,
DGX Spark, Coiled) write results to the same BigQuery table. The analysis notebook reads
from BigQuery; it never touches SQLite or PostgreSQL directly.

For the full record of alternatives considered (Ray, JupyterHub, Temporal, Coiled,
custom FastAPI), see `docs/architecture-decisions.md`.

---

## The Validation Challenge: SteinSense

Phase 2 design decisions are driven by a concrete research study, not by abstract
requirements alone. The SteinSense GPU implementation paper
(`docs/design/implementation-paper-proposal-v7-xla-tpu.md`) is the primary validation
challenge for the EMS design.

The study implements a single AMP algorithm (SteinSense) across a 14-cell backend matrix
(7 GPU stacks × 2 Jacobian variants) on 4 hardware tiers (Sherlock A100, Marlowe H100,
DGX Spark GB10, plus CPU baseline), with a controlled parameter sweep across (N, B, δ,
signal distribution, seed). EMS is named as the dispatch infrastructure; BigQuery as the
unified result store (paper Contribution 7).

This study stresses EMS in the following ways:

| Requirement | EMS gap | Phase 2 item |
|-------------|---------|--------------|
| `implementation`, `hardware` as result columns | Works today — just params | Convention, not code |
| `seed` as explicit sweep parameter | Works today | Convention, not code |
| Multi-cluster dispatch to one BigQuery table | Needs coordination design | Prefect integration |
| Git hash per result row | Not captured | R-6 (moved to item 2) |
| Experiment registry: what ran, with what code | Missing | Registry (item 3) |
| Progress visualization across 6 axes | Heatmap design incomplete | Design doc needed |
| R-9 multi-row injection (AMP iterations) | Not implemented | R-9 (item 1) |

The core sweep is tractable (N ≤ 5,000 for most cells; N = 10⁶ only on Marlowe).
Current `Databases` write batching requires no changes for this scale.

---

## Design Process

We are in the design phase. Each design decision produces a document in `docs/design/`
before any implementation begins. The sequence:

1. Write the design document
2. Validate it against the SteinSense study requirements
3. Identify conflicts or gaps
4. Resolve open questions
5. Record the decision in `docs/architecture-decisions.md`
6. Then implement

**Current design artifacts:**

| File | Status | Purpose |
|------|--------|---------|
| `notebook-prototype-v1.md` | Draft — one open question | Standardized experiment notebook structure |
| `implementation-paper-proposal-v7-xla-tpu.md` | Complete | SteinSense paper spec; primary validation challenge |
| `phase2-plan.md` | This document | Overall plan and architecture |

**Design agenda — documents to produce next:**

1. `steinsense-experiment-dict.md` — the actual experiment dict for the SteinSense sweep;
   forces decisions on parameter schema and seed convention
2. `steinsense-results-schema.md` — what the SteinSense callable returns; drives R-9 design
3. `progress-visualization.md` — how to show completion across 6 parameter dimensions;
   resolves the open question in `notebook-prototype-v1.md`
4. `experiment-registry-design.md` — AD-5 decision: BigQuery table vs. JSON directory
   vs. Prefect Flow metadata; must resolve before hub work begins
5. `multi-cluster-coordination.md` — how one experiment dict dispatches across Sherlock,
   Marlowe, and DGX Spark with results landing in one BigQuery table

---

## Phase 2 Work Items

### Item 0 — Package Refactor (Prerequisite)

**Must be done before any feature work.**

`manager.py` is a 600-line god module. Phase 2 features (storage abstraction, registry,
Prefect integration) cannot be added cleanly without first splitting it into a package.

Target package layout:

```
src/EMS/
  __init__.py      — public API exports
  storage.py       — Databases, StorageBackend abstraction
  cluster.py       — EvalOnCluster, do_on_cluster, do_experiment
  registry.py      — experiment record, registry
  utils.py         — unroll_parameters_gpt, dedup, JSON helpers
```

The `StorageBackend` abstraction replaces the current 4× duplicated if/elif dispatch
chains in `read_params()`, `read_table()`, and `_push_to_database()`. The public API
does not change.

**Design document needed:** No — the target layout is clear. Enter plan mode, then implement.

---

### Item 1 — R-9: Parameter Injection

EMS automatically injects all input parameter keys into every result row before storage.
Researchers stop manually including parameters in their returned DataFrames.

**The multi-row case (critical for SteinSense / AMP):** Some callables return multiple
rows per parameter combination — e.g., one row per AMP iteration. EMS must inject the
full input parameter dict into every emitted row, not just the first.

**Design document needed:** Yes — `steinsense-results-schema.md` will clarify whether
the SteinSense callable is single-row or multi-row, which determines the injection
complexity needed for this study.

---

### Item 2 — R-6: Git Hash Capture (moved up)

EMS captures and records the git hash of the research project code at experiment launch
time — not just the EMS version. Stored in every result row (or in the experiment
registry record if the registry lands first).

**Why moved up from item 4:** The SteinSense paper's correctness claims depend on
knowing which code version produced which results. With 14 implementations running over
months, this is not optional. The audit trail is a paper deliverable.

**Design document needed:** Covered in `steinsense-results-schema.md` (which columns
does each result row carry?) and `experiment-registry-design.md` (does the hash live
in each row or in a registry record?).

---

### Item 3 — Experiment Registry (AD-5 — open decision)

A queryable record of every experiment that has run: researcher, project, table name,
date, git hash of experiment code, EMS version, cluster used, and link to the design
document / notebook.

**Three options under consideration:**

| Option | Pros | Cons |
|--------|------|------|
| BigQuery table | Queryable with the same tool as results; no new infrastructure | Requires BigQuery credentials at launch time |
| Structured JSON directory | Zero dependencies; human-readable; git-trackable | Not queryable across machines; grows without bound |
| Prefect Flow metadata | Free if Prefect is already running; UI search for free | Requires Prefect to be running; not queryable via SQL |

**Design document needed:** `experiment-registry-design.md` — the SteinSense study
makes the requirements concrete enough to decide.

**Blocking:** This decision must be made before Item 4 (Prefect integration), because the
registry design affects how Prefect Flows are structured and tagged.

---

### Item 4 — Prefect Integration

Wrap `do_on_cluster()` as a Prefect Flow. Deploy Prefect Server on the Mac Pro as a
persistent `launchd` service. Expose the Prefect dashboard via Tailscale.

The existing `do_on_cluster()` function signature does not change. The Flow is a thin
wrapper that adds persistent execution semantics:

```python
from prefect import flow

@flow(name="ems-experiment")
def run_experiment(experiment: dict, cluster_config: dict):
    db = setup_database(experiment['table_name'])
    client = setup_cluster(cluster_config)
    do_on_cluster(experiment, callable_fn, client, db)
```

**Multi-cluster routing:** The `cluster_config` dict parameterizes which cluster to use
(LocalCluster, SLURMCluster on Sherlock, SLURMCluster on Marlowe, Coiled). Same
experiment dict; different cluster config. Results from all clusters land in the same
BigQuery table because `table_name` is fixed in the experiment dict.

**Design document needed:** `multi-cluster-coordination.md` — how cluster config is
structured and how Prefect routes to each.

**Blocking:** Items 0–3 must be complete first.

---

### Item 5 — R-11: Common Result Utilities

EMS ships first-class utilities that researchers currently copy-paste into every project:

- Groupby aggregation across Monte Carlo replicates (mean, std, count)
- SQLite → BigQuery sync
- Result subset export to CSV

Confirmed duplication: identical `stack_results.py`, `copy_results_to_cloud.py`, and
`write_to_gbq.py` found across multiple researcher project repos.

**Design document needed:** No — scope is well-defined. Implement after Item 4.

---

### Item 6 — R-12: Variable-Length Output Helper

A convention or helper for callables that return variable-length arrays (e.g., singular
values whose count depends on input matrix dimensions). Researchers should not be
responsible for computing maximum output dimensions and padding results to a fixed
DataFrame width manually.

**Design document needed:** Yes — the padding strategy (NaN fill vs. separate
dimension column vs. sparse storage) is a design choice with downstream query
implications.

---

### Item 7 — R-10: `derive_params()`

A native pattern for multi-phase experiments: given an upstream result table and a
researcher-supplied transformation function, produce the parameter list for a downstream
experiment. Replaces the CSV hand-off pattern observed in Milad B's research.

**Design document needed:** Yes — the API shape needs design before implementation.

---

## Open Questions

These must be resolved during the design phase, in the order they block work items:

| # | Question | Blocks | Status |
|---|----------|--------|--------|
| 1 | Experiment registry: BigQuery table vs. JSON dir vs. Prefect metadata? | Item 4 | Open — `experiment-registry-design.md` needed |
| 2 | Where does the git hash live — in each result row, or in a registry record? | Items 2, 3 | Open — resolved by Items 2+3 design docs |
| 3 | SteinSense callable: single-row or multi-row output? | Item 1 | Open — `steinsense-results-schema.md` needed |
| 4 | Progress heatmap for N>2 axes: edit-the-cell vs. ipywidgets? | `notebook-prototype-v1.md` | Open |
| 5 | Failure handling: re-queue, flag, or log and skip? | Item 4 | Open |
| 6 | Cost tracking per experiment? | Item 3 | Open |

---

## What Is Not Changing

- Public API of `do_on_cluster()`, `Databases`, `EvalOnCluster` — no breaking changes
- The experiment dict format — `table_name`, `params`, `stop_list` stay as-is
- Dask as the compute engine
- BigQuery as the analysis contract
- The 22 existing unit tests — all must continue to pass through the refactor
