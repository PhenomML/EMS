# EMS Project Memory

This file is committed to the repo so that any Claude Code instance on any machine
starts with the same shared context. Update it via `Edit` or `Write` and commit the change.
Read `docs/VISION.md` and `docs/architecture-decisions.md` at the start of every session.

---

## What This Project Is

EMS (Experiment Management System) for the Stanford Donoho Lab. A Python library for
managing embarrassingly parallel scientific computation experiments across Dask clusters,
storing results in SQLite / PostgreSQL / BigQuery.

**v1.0.0 is live on `main`** (fast-forward merged from RC1, tagged `v1.0.0`, 2026-04-25).
**Phase 2** is active on branch `claude-v2.0.0_phase2`.

---

## Key Documents

| Document | Purpose |
|----------|---------|
| `docs/VISION.md` | Requirements R-1–R-12, chosen architecture, phased plan. Primary working doc. |
| `docs/architecture-decisions.md` | Every significant architectural choice with alternatives examined and rationale. |
| `docs/design/` | Design docs, proposals, experiment records. "Experimental notebooks" live here. |
| `docs/design/notebook-prototype-v1.md` | Standardized experiment notebook section structure; 3 prototype variants. |
| `docs/design/implementation-paper-proposal-v7-xla-tpu.md` | SteinSense paper proposal — primary validation challenge for EMS Phase 2 design. |
| `docs/user-stories/` | US-001–US-006, grounded in real researcher code reviews. |
| `docs/EMS_Model.md` | Original PI model: four DB tables (Experiment, Experimenter, Project, Funding). |
| `docs/claude/MEMORY.md` | This file. |
| `CLAUDE.md` | Dev guidance for Claude instances. |

---

## Repository & Infrastructure

- **Git remote**: `git@adonoho-GitHub:PhenomML/EMS.git` (SSH key `adonoho-GitHub`)
- **Hub server**: Intel Mac Pro, Tailscale-accessible. Phase 2 runs here.
- **Compute**: 2× NVIDIA DGX Spark (Tailscale); Stanford Sherlock (SLURM); GCP via Coiled.
- **Storage**: local SQLite (`data/EMS.db3`), PostgreSQL via Cloud SQL Proxy, BigQuery.
- **conda env**: `EMS` (Python 3.11). Tests: `conda run -n EMS python -m pytest tests/`
- **Editable install**: `conda run -n EMS pip install -e .`
- **pytest**: not in `environment.yml` — `pip install pytest` if missing.

---

## Branch Map

| Branch | Status |
|--------|--------|
| `main` | v1.0.0 live — tagged, pushed 2026-04-25 |
| `claude-v1.0.0_RC1` | Merged to main; do not develop here |
| `claude-v2.0.0_phase2` | Active Phase 2 development |

---

## Architecture Decisions (summary — full record in `docs/architecture-decisions.md`)

**AD-1: Dask chosen over Ray.**
Dask embraces the DataFrame as primary abstraction, matching the data science community.
Ray's Actor model is an unnecessary abstraction for embarrassingly parallel sweeps.

**AD-2: Prefect Server on Mac Pro as hub orchestration layer.**
Satisfies the core Phase 2 requirement: researcher launches experiment from hub,
disconnects, checks status via URL from any device. Prefect owns job lifecycle and
history; Dask owns compute; BigQuery is the data contract.

Temporal was evaluated and rejected: EMS's `dedup_experiment()` already provides
data-layer restart guarantees, making Temporal's durable execution redundant for this
use case. Prefect's lower operational complexity wins.

```
Researcher (any device, Tailscale)
        │
   ┌────┴─────────────────────┐
   │                          │
   ▼                          ▼
Prefect Server            Dask Dashboard
(job submit / history /   (live cluster view,
 experiment registry)      free while cluster runs)
        │ DaskTaskRunner
        ▼
   Dask Cluster  ────writes────▶  BigQuery / SQLite
   (Sherlock / DGX Spark / GCP)
```

**AD-3: Storage** — SQLite (local durability) + PostgreSQL (relational access) +
BigQuery (analytical frontend). BigQuery is the contract between compute and analysis.
For multi-cluster work (SteinSense paper), BigQuery is the **primary** result store.

**AD-4: Python 3.11 for v1.0; Python 3.12 for v1.1.** 3.13 deferred.

---

## SteinSense Paper — Primary EMS Validation Challenge

`docs/design/implementation-paper-proposal-v7-xla-tpu.md` describes a systematic
multi-backend GPU implementation study of the SteinSense AMP algorithm. EMS is named
as the dispatch infrastructure and BigQuery as the unified result store (Contribution 7).

Key requirements this places on EMS:
- `implementation` and `hardware` as first-class sweep parameters (columns in results)
- `seed` as explicit sweep parameter (controlled RNG for cross-implementation joins)
- Multi-cluster dispatch: same experiment dict → Sherlock, Marlowe, DGX Spark
- BigQuery as primary store (all clusters write to one table)
- R-6 (git hash) is an audit trail requirement, not optional
- Experiment registry must track which implementations ran, with what code version

The core sweep is tractable (N ≤ 5000 for most cells); N=10⁶ is Marlowe-only.
Current `Databases` write batching handles this scale without modification.

Design agenda (in order — each produces a `docs/design/` document):
1. SteinSense experiment dict (parameter schema)
2. SteinSense results schema (what the callable returns)
3. Progress visualization for 6-dimensional space
4. AD-5: experiment registry — forced decision by this study
5. Multi-cluster coordination design

---

## Phase 2 — Work Items (priority order, updated 2026-04-25)

### 0. Architecture prerequisite (do before any feature work)
Refactor `manager.py` into a package:
- `storage.py` — `Databases`, `StorageBackend` abstraction (replaces 4× if/elif dispatch)
- `cluster.py` — `EvalOnCluster`, `do_on_cluster`, `do_experiment`
- `registry.py` — experiment record, registry
- `utils.py` — parameter unrolling, dedup, JSON helpers

### 1. R-9: Parameter injection
EMS injects input params into every result row automatically. Must handle multi-row
returns (e.g., AMP researcher emits one row per iteration, not per param combo).

### 2. R-6: Git hash capture (moved up from item 4)
Capture git hash of research project code (not only EMS version) at run time.
Required audit trail for SteinSense 14-cell implementation matrix.

### 3. Experiment registry (AD-5 — decision pending)
Queryable record: researcher, project, date, git hash, linked notebook.
Options: embedded BigQuery table, structured JSON directory, Prefect Flow metadata.
**Must resolve before hub work begins. SteinSense study makes requirements concrete.**

### 4. Prefect integration
Wrap `do_on_cluster()` as a Prefect Flow. Deploy Prefect Server on Mac Pro as a
persistent service (launchd plist). Expose Dask dashboard via Tailscale.

### 5. R-11: Common result utilities
Groupby aggregation, SQLite→cloud sync, CSV export — built into EMS, not copy-pasted.

### 6. R-12: Variable-length output helper
Padding helper so researchers don't compute max output dimensions manually.

### 7. R-10: `derive_params()`
Upstream result table + transformation function → parameter list for downstream experiment.
Replaces CSV hand-off between multi-phase experiments.

---

## Researcher Profiles (from code reviews)

**Apratim Dey (power researcher)** — AMP_matrix_recovery:
- 14 scripts, 70+ branches, 116 JSON files, SLURM + Coiled at scale
- Pain: no notebooks, manual param injection, CWD JSON scatter, no failure record
- Key: multi-row results per callable (one row per AMP iteration) — R-9 must handle this

**Milad B (standard researcher)** — MatrixCompletion / Matrix_Denoising:
- Multi-phase experiments with CSV hand-off between phases
- Duplicate utility scripts across projects; manual variable-length output padding
- Analysis notebook in a completely separate disconnected repo

---

## Open Questions (3 — see VISION.md)

1. **Experiment registry implementation**: BigQuery table vs. JSON directory vs.
   Prefect Flow metadata? **Must resolve before hub work begins.**
2. **Failure handling**: re-queue, flag for review, or log and skip? Default behavior?
3. **Cost tracking**: record cloud compute cost per experiment; charge to funding account?

---

## Workflow / Preferences

- Read `docs/VISION.md` and `docs/architecture-decisions.md` at session start.
- Commit after each meaningful unit of work; push via `git push`.
- One Claude Code instance per project in a tmux session on the Mac Pro.
- Enter plan mode before non-trivial implementation.
- Concise, direct responses preferred.
- New architectural choices → new AD entry in `docs/architecture-decisions.md`.
- Design documents and experiment records live in `docs/design/`.
- Stay in design phase: use SteinSense study to validate each EMS design decision
  before implementation begins.
