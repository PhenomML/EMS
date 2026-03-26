# EMS Project Memory

This file is committed to the repo so that any Claude Code instance on any machine
starts with the same shared context. Update it via `Edit` or `Write` and commit the change.

## What This Project Is

EMS (Experiment Management System) for the Stanford Donoho Lab. Currently a single-module
Python library (`src/EMS/manager.py`) for managing embarrassingly parallel scientific
computation experiments across Dask clusters, storing results in SQLite/PostgreSQL/BigQuery.

The current library is **Phase 1**. We are planning **Phase 2**: a web-based computational
hub ("tree of notebooks" server + dashboard). See `docs/VISION.md` for the full requirements.

## Key Documents

- `docs/VISION.md` — requirements, open questions, architectural vision. Primary working document.
- `docs/user-stories/` — US-001 through US-006, grounded in real researcher usage.
- `docs/claude/MEMORY.md` — this file; shared Claude context committed to the repo.
- `CLAUDE.md` — architecture and dev guidance for Claude instances.

## Infrastructure Context

- **Hub server**: Intel Mac Pro, accessible via Tailscale. Must remain deployable on any
  standard Linux server (no cloud-specific runtime dependencies).
- **Compute**: 2× NVIDIA DGX Spark on same Tailscale network; SLURM HPC (Stanford Sherlock);
  AWS/GCP/Azure cloud clusters.
- **Storage backends**: local SQLite, remote PostgreSQL (Cloud SQL), Google BigQuery.
- **Git push**: configured via SSH using `adonoho-GitHub` key; remote set to
  `git@adonoho-GitHub:PhenomML/EMS.git`.

## Collaboration Model

The PI (Donoho) and the researcher are geographically distributed. Preferred collaboration
mode is a shared `tmux` session on the Mac Pro hub (accessible via Tailscale), so both can
work with the same Claude Code instance simultaneously. Claude Code is installed per-user on
each machine; context travels via this committed memory file and `CLAUDE.md`.

## Current State (as of 2026-03-26)

We are in **requirements gathering and user story phase** for Phase 2. No Phase 2 code
has been written yet. The work so far this sprint:

1. **Architectural review of Phase 1** (`src/EMS/manager.py`) completed. Key findings:
   - God module (610 lines, no internal separation) — must be split before Phase 2
   - Backend dispatch duplicated 4× (if/elif chains per method) — needs StorageBackend abstraction
   - Raw SQL constructed from unsanitized input — SQL injection risk
   - Silent failure on write errors — data loss risk
   - `record_experiment()` writes to CWD — needs configurable path
   - R-9 (parameter injection) not yet implemented
   - Dead code: `unroll_parameters()`, `update_index()`, `do_test_experiment()` stub

2. **Two-system architecture clarified** (PI observation):
   - Backend: experiment spec → cluster dispatch → SQL database
   - Frontend: notebook environment (Python or R) → reads from SQL database
   - The SQL database (BigQuery) is the contract between the two systems.

3. **User stories written** (US-001 through US-006), grounded in code review of real projects:
   - AMP_matrix_recovery (power researcher, Apratim Dey): 14 scripts, 70+ branches,
     116 JSON files, thousands of param combos, zero analysis notebooks
   - MatrixCompletion + Matrix_Denoising + MiladB90 (standard researcher, Milad B):
     multi-phase CSV hand-off, duplicate utility scripts, variable-length output padding,
     analysis notebook in separate disconnected repo
   - BSky2GBQ: data pipeline using `local_db=False` and `EvalOnCluster` async API;
     validates these as first-class use cases; not a requirements source

## Requirements Status (R-1 through R-12)

All defined in `docs/VISION.md`. Key decisions and status:

- **R-9**: At v1.0, EMS injects input parameters into result DataFrames automatically.
  Pre-v1.0, researchers must include params themselves. **Not yet implemented.**
  Must handle multi-row returns (some callables emit multiple rows per param combo).
- **R-10 (sharpened)**: Real pattern is `derive_params()` — run experiment A, apply
  transformation to results, produce parameter list for experiment B. CSV hand-off
  is the current painful workaround.
- **R-11 (new)**: Common result utilities (groupby aggregation, SQLite→cloud sync,
  CSV export) — currently copy-pasted into every project.
- **R-12 (new)**: Variable-length output support — researchers currently compute max
  output dimension manually and pad DataFrames.
- **R-6**: Git hash capture must cover research project code, not only EMS version.
- **R-7 (Dashboard)**: In scope for Phase 2.
- **R-8**: Namespacing by researcher/project is required.

## Open Questions (3 remaining)

1. **Experiment registry** — Confirmed required (not optional) by both researchers.
   Both used git branches as a substitute (70+ and 30+ branches respectively).
   Implementation TBD: embedded DB table, sidecar JSON directory, or separate service.
2. **Failure handling** — Silent drops observed in both researcher projects. Default
   behavior TBD; must be dynamically changeable.
3. **Cost tracking** — Cloud compute costs recorded per experiment; funding account
   specified in experiment definition.

## Key Design Principles (from VISION.md)

- Make the right thing the default (scaffold notebooks, capture versions automatically)
- The database is the contract (all data through SQL; nothing important in files only)
- Friction kills science (minimize steps from run completion to visible results)
- Don't make researchers reinvent utilities (aggregation, sync, export belong in EMS)

## Next Logical Steps

1. Discuss Phase 2 architecture with PI — the user stories and requirements are now
   rich enough to support a real design conversation.
2. Decide on the experiment registry implementation approach (open question 1).
3. Plan the Phase 1 refactor needed before Phase 2 can be built:
   - Split `manager.py` into package structure
   - Introduce `StorageBackend` abstraction
   - Fix SQL injection in `read_params()`
   - Implement failure logging for failed futures

## Workflow / Preferences

- Read `docs/VISION.md` fresh at the start of each session before discussing requirements.
- Commit after each meaningful unit of work; push via `git push` (SSH configured).
- PI (Donoho) is an active stakeholder; shares doc for review between sessions.
- One Claude Code instance per active GitHub project, in a tmux session.
- Restart Claude after major topic boundaries; update this file before restarting.
