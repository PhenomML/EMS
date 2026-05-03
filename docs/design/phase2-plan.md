# EMS Phase 2 — Architecture & Plan

**Date:** 2026-05-03
**Updated:** 2026-05-03 — Item 4 split; JupyterHub added as Phase 2 surface layer (AD-5)
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

Phase 2 adds two hub-layer services to the Mac Pro: JupyterHub as the notebook surface
and Prefect Server as the job orchestration layer.

```
Researcher (any device, Tailscale)
        │
   ┌────┼─────────────────────────────┐
   │    │                             │
   ▼    ▼                             ▼
JupyterHub              Prefect Server           Dask Dashboard
(edit notebooks /       (job execution /         (live cluster view)
 submit to Prefect /     history / registry)
 run analysis)                  │
        │                DaskTaskRunner
        │ submit_experiment()   │
        └──────────────▶  Dask Cluster ──writes──▶  BigQuery / SQLite
   (Sherlock / DGX Spark / Coiled on GCP)           ▲
                                                     │ reads
                                             Analysis Notebooks
                                             (running in JupyterHub)
```

**JupyterHub** runs as a `launchd` service on the Mac Pro, Tailscale-accessible.
Researchers edit experiment notebooks, submit to Prefect, and run BigQuery analysis —
all from a browser, from any device. Notebooks live in git repos and are pulled into
JupyterHub on demand; JupyterHub is the interface, not the store. See AD-5.

**Prefect Server** runs as a second `launchd` service on the Mac Pro. The JupyterHub
kernel submits a Prefect Flow via `submit_experiment()` and can immediately die;
the experiment runs to completion server-side. Job status, logs, and run history are
visible from any device via Tailscale URL.

**Dask** remains the compute engine. Prefect owns the job lifecycle; Dask owns the
parallel dispatch. `do_on_cluster()` maps directly onto a Prefect Flow with a thin
wrapper — no change to the existing dispatch logic.

**BigQuery** is the data contract for multi-cluster work. All clusters write results to
the same BigQuery table. Analysis notebooks in JupyterHub read from BigQuery directly.

For the full record of alternatives considered (Ray, Temporal, Marimo, VS Code Server,
local-only Jupyter), see `docs/architecture-decisions.md` (AD-2, AD-5).

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
| `notebook-prototype-v3.md` | Draft — open questions tracked in `open-questions.md` | Standardized experiment notebook structure (current version) |
| `implementation-paper-proposal-v7-xla-tpu.md` | Complete | SteinSense paper spec; primary validation challenge |
| `open-questions.md` | Living — 11 open questions | Consolidated tracker for all unresolved design questions |
| `phase2-plan.md` | This document | Overall plan and architecture |

**Design agenda — documents to produce next:**

1. `steinsense-results-schema.md` — what the SteinSense callable returns (single-row vs.
   multi-row); drives R-9 design and resolves OQ-4
2. `progress-visualization.md` — completion visualization across N>2 parameter dimensions;
   resolves OQ-8
3. `experiment-registry-design.md` — OQ-6 decision: BigQuery table vs. JSON directory
   vs. Prefect Flow metadata; must resolve before hub work begins
4. `multi-cluster-coordination.md` — how one experiment dict dispatches across Sherlock,
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

### Item 4a — JupyterHub Deployment

Deploy JupyterHub on the Mac Pro as a `launchd` service, accessible to the team via
Tailscale. Configure multi-user kernel isolation. Connect to researcher project repos
via git pull on demand.

**Purpose:** Validate the notebook-as-spec workflow with real researchers before the
Prefect integration is complete. Even without Prefect wired up, researchers can use
JupyterHub for:
- Editing experiment specification notebooks
- Running BigQuery analysis notebooks from any device
- Browsing the experiment registry (once it exists)

**What we are measuring:** Do researchers actually open JupyterHub, or do they fall
back to local Jupyter and SSH? The answer shapes whether the Phase 3 design is built
around JupyterHub as the primary interface.

**Can start:** Immediately after Item 0 (package refactor). Independent of Items 1–3
and Item 4b.

**Design document needed:** No — JupyterHub installation and configuration is
operational, not a design decision. AD-5 records the architectural choice.

---

### Item 4b — Prefect Integration

Wrap `do_on_cluster()` as a Prefect Flow. Deploy Prefect Server on the Mac Pro as a
persistent `launchd` service alongside JupyterHub.

The existing `do_on_cluster()` function signature does not change. The Flow is a thin
wrapper that adds persistent execution semantics:

```python
from prefect import flow

@flow(name="ems-experiment")
def run_experiment(experiment: dict, cluster_config: dict):
    db = setup_database(experiment['table_name'])
    client = setup_cluster(cluster_config)
    do_on_cluster(experiment, client, db)
```

**Multi-cluster routing:** The `cluster_config` dict parameterizes which cluster to use
(LocalCluster, SLURMCluster on Sherlock, SLURMCluster on Marlowe, Coiled). Same
experiment dict; different cluster config. Results from all clusters land in the same
BigQuery table because `table_name` is fixed in the experiment dict.

**Can start:** After Items 0–3. Independent of Item 4a.

**Design document needed:** `multi-cluster-coordination.md` — how cluster config is
structured and how Prefect routes to each target.

---

### Item 4c — JupyterHub → Prefect Submission Wiring

Connect JupyterHub notebooks to Prefect Server: implement `submit_experiment()` as the
single notebook cell that submits a Prefect Flow and returns immediately.

```python
from EMS.flows import submit_experiment

run_url = submit_experiment(experiment, cluster_config)
print(f'Track at: {run_url}')
```

This is the end-to-end fire-and-forget workflow: researcher edits the experiment dict
in JupyterHub, runs `submit_experiment()`, closes the browser, checks Prefect UI from
phone.

**Requires:** Items 4a and 4b both complete.

**This is the primary usability validation point for the Phase 2 hub architecture.**

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

Tracked in `docs/design/open-questions.md` (living document, 11 questions).
Key blocking questions in priority order:

| OQ | Question | Blocks |
|----|----------|--------|
| OQ-4 | SteinSense callable: single-row or multi-row? | R-9 design (Item 1) |
| OQ-6 | Experiment registry implementation | Items 4b, 4c |
| OQ-7 | Git hash: per-row vs. registry record | Items 2, 3 |
| OQ-1 | Worker import path for callable | Item 4b |
| OQ-10 | Failure handling default | Item 4b |

---

## What Is Not Changing

- Public API of `do_on_cluster()`, `Databases`, `EvalOnCluster` — no breaking changes
- The experiment dict format — `table_name`, `params`, `stop_list` stay as-is
- Dask as the compute engine
- BigQuery as the analysis contract
- The 22 existing unit tests — all must continue to pass through the refactor
