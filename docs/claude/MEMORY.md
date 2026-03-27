# EMS Project Memory

This file is committed to the repo so that any Claude Code instance on any machine
starts with the same shared context. Update it via `Edit` or `Write` and commit the change.

## What This Project Is

EMS (Experiment Management System) for the Stanford Donoho Lab. A Python library for
managing embarrassingly parallel scientific computation experiments across Dask clusters,
storing results in SQLite / PostgreSQL / BigQuery.

**v1.0.0 is complete and in RC testing** (branch `claude-v1.0.0_RC1`, announced to team
2026-03-27). Phase 2 development begins on branch `claude-v2.0.0_phase2`.

## Key Documents

- `docs/VISION.md` — requirements R-1 through R-12, open questions, architectural vision.
- `docs/user-stories/` — US-001 through US-006, grounded in real researcher code reviews.
- `docs/claude/MEMORY.md` — this file; shared Claude context committed to the repo.
- `CLAUDE.md` — architecture and dev guidance for Claude instances.

## Repository & Infrastructure

- **Git remote**: `git@adonoho-GitHub:PhenomML/EMS.git` (SSH key `adonoho-GitHub`)
- **Hub server**: Intel Mac Pro, accessible via Tailscale. Phase 2 server must run here;
  no cloud-specific runtime dependencies.
- **Compute**: 2× NVIDIA DGX Spark (Tailscale); Stanford Sherlock (SLURM); AWS/GCP/Azure.
- **Storage**: local SQLite (`data/EMS.db3`), PostgreSQL via Cloud SQL Proxy, BigQuery.
- **conda env**: `EMS` (Python 3.11). Run tests: `conda run -n EMS python -m pytest tests/`
- **Install editable**: `conda run -n EMS pip install -e .`

## Branch Map

| Branch | Purpose |
|--------|---------|
| `main` | Stable releases |
| `claude-v1.0.0_RC1` | v1.0 RC — in team review (do not develop here) |
| `claude-v2.0.0_phase2` | Active Phase 2 development |

## v1.0.0 — What Was Done

Single source file `src/EMS/manager.py`. All changes in one commit on `claude-v1.0.0_RC1`:

1. Dead code removed: `unroll_parameters()`, `update_index()`, `do_test_experiment()`,
   `_df_size_check()`, `EvalOnCluster.result/eval_params/__aiter__/__anext__`
2. SQL injection fixed: `read_params()` / `read_table()` use double-quoted identifiers +
   `sqlalchemy.text()`; helpers `_safe_column_list()`, `_safe_table_name()`
3. EvalOnCluster hardened: `RuntimeError` guards, failed-future warning logs,
   `key_from_params` raises `ValueError` on key mismatch
4. Logging: WARNING → INFO for normal operations
5. Google-style docstrings on all public API
6. `tests/test_manager.py`: 22 unit tests, all passing (no cluster/DB needed)
7. Full `README.md` written
8. Version bumped to 1.0.0 in `pyproject.toml` and `environment.yml`

**Note**: `unroll_parameters_gpt({})` now returns `[]` (empty-dict guard added).

## Phase 2 — What Needs to Be Built

See `docs/VISION.md` for full requirements. Key Phase 2 work items in priority order:

### Must-have for v2.0
- **R-9**: EMS injects input params into every result row automatically. Must handle
  multi-row returns (e.g., AMP researcher emits one row per iteration, not per param combo).
- **Experiment registry**: Queryable record of what ran, when, with which code version.
  Implementation TBD (open question 1 in VISION.md). Both researchers used 30–70 git
  branches as a substitute — confirms this is non-optional.
- **R-6**: Capture git hash of *research project code*, not only EMS version.
- **R-11**: Common result utilities built into EMS (groupby aggregation, SQLite→cloud sync,
  CSV export) — currently copy-pasted into every researcher project.
- **R-12**: Variable-length output helper — researchers currently pad DataFrames manually.

### Architecture prerequisite (do first)
Before Phase 2 features, `manager.py` must be refactored:
- Split into package structure (`__init__.py`, `storage.py`, `cluster.py`, `registry.py`, etc.)
- Introduce `StorageBackend` abstraction to replace 4× duplicated if/elif dispatch
- `record_experiment()` path must be configurable (currently hardcoded to CWD)

### Phase 2 server (hub)
- "Tree of notebooks" web server — project registry dashboard accessible to team
- Scaffolds analysis notebooks automatically on first experiment (US-003)
- Live computation progress dashboard (R-7)
- Must run on the Intel Mac Pro hub; no cloud runtime deps

## Researcher Profiles (from code reviews)

**Apratim Dey (power researcher)** — AMP_matrix_recovery:
- 14 experiment scripts, 70+ branches, 116 JSON files, SLURM + Coiled at scale
- Pain: no notebooks, manual param injection, CWD JSON scatter, no failure record
- Key finding: multi-row results per callable (one row per AMP iteration)

**Milad B (standard researcher)** — MatrixCompletion / Matrix_Denoising:
- Multi-phase experiments with CSV hand-off between phases
- Duplicate utility scripts across projects; variable-length output padding by hand
- Analysis notebook in a completely separate disconnected repo

## Open Questions (3 remaining — see VISION.md)

1. **Experiment registry implementation**: embedded DB table vs. structured JSON directory
   vs. separate service?
2. **Failure handling**: re-queue automatically, flag for review, or log and skip?
   Must have a default and be dynamically changeable.
3. **Cost tracking**: record cloud compute cost per experiment, charge to funding account?

## Workflow / Preferences

- Read `docs/VISION.md` at start of every session before discussing requirements.
- Commit after each meaningful unit of work; push via `git push`.
- One Claude Code instance per project in a tmux session; context travels via this file.
- Restart Claude after major topic shifts; update this file before restarting.
- User prefers concise, direct responses. Enter plan mode before non-trivial implementation.
