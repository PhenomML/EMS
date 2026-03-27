# EMS Project Memory

This file is committed to the repo so that any Claude Code instance on any machine
starts with the same shared context. Update it via `Edit` or `Write` and commit the change.
Read `docs/VISION.md` and `docs/architecture-decisions.md` at the start of every session.

---

## What This Project Is

EMS (Experiment Management System) for the Stanford Donoho Lab. A Python library for
managing embarrassingly parallel scientific computation experiments across Dask clusters,
storing results in SQLite / PostgreSQL / BigQuery.

**v1.0.0 RC** is in team review (branch `claude-v1.0.0_RC1`, announced 2026-03-27).
**Phase 2** is active on branch `claude-v2.0.0_phase2`.

---

## Key Documents

| Document | Purpose |
|----------|---------|
| `docs/VISION.md` | Requirements R-1–R-12, chosen architecture, phased plan. Primary working doc. |
| `docs/architecture-decisions.md` | Every significant architectural choice with alternatives examined and rationale. |
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
| `main` | Stable releases |
| `claude-v1.0.0_RC1` | v1.0 RC — in team review; do not develop here |
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

**AD-4: Python 3.11 for v1.0; Python 3.12 for v1.1.** 3.13 deferred.

---

## v1.0.0 — What Was Done (single commit on `claude-v1.0.0_RC1`)

1. Dead code removed: `unroll_parameters()`, `update_index()`, `do_test_experiment()`,
   `_df_size_check()`, `EvalOnCluster.result/eval_params/__aiter__/__anext__`
2. SQL injection fixed: double-quoted identifiers + `sqlalchemy.text()`;
   helpers `_safe_column_list()`, `_safe_table_name()`
3. EvalOnCluster hardened: `RuntimeError` guards; failed-future warning logs;
   `key_from_params` raises `ValueError` on key mismatch
4. Logging: WARNING → INFO for normal operations
5. Google-style docstrings on all public API
6. `tests/test_manager.py`: 22 unit tests, all passing
7. Full `README.md` written
8. Version bumped to 1.0.0 in `pyproject.toml` and `environment.yml`
9. `unroll_parameters_gpt({})` now returns `[]` (empty-dict guard added)

---

## Phase 2 — Work Items (priority order)

### 0. Architecture prerequisite (do before any feature work)
Refactor `manager.py` into a package:
- `storage.py` — `Databases`, `StorageBackend` abstraction (replaces 4× if/elif dispatch)
- `cluster.py` — `EvalOnCluster`, `do_on_cluster`, `do_experiment`
- `registry.py` — experiment record, registry
- `utils.py` — parameter unrolling, dedup, JSON helpers

### 1. R-9: Parameter injection
EMS injects input params into every result row automatically. Must handle multi-row
returns (e.g., AMP researcher emits one row per iteration, not per param combo).

### 2. Experiment registry (AD-5 — decision pending)
Queryable record: researcher, project, date, git hash, linked notebook.
Options: embedded BigQuery table, structured JSON directory, Prefect Flow metadata.
**This decision must be made before hub server work begins.**

### 3. Prefect integration
Wrap `do_on_cluster()` as a Prefect Flow. Deploy Prefect Server on Mac Pro as a
persistent service (launchd plist). Expose Dask dashboard via Tailscale.

### 4. R-6: Git hash capture
Capture git hash of research project code (not only EMS version) at run time.

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
