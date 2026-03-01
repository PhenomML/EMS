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
- `docs/claude/MEMORY.md` — this file; shared Claude context committed to the repo.
- `CLAUDE.md` — architecture and dev guidance for Claude instances.

## Infrastructure Context

- **Hub server**: Intel Mac Pro, accessible via Tailscale. Must remain deployable on any
  standard Linux server (no cloud-specific runtime dependencies).
- **Compute**: 2× NVIDIA DGX Spark on same Tailscale network; SLURM HPC (Stanford Sherlock);
  AWS/GCP/Azure cloud clusters.
- **Storage backends**: local SQLite, remote PostgreSQL (Cloud SQL), Google BigQuery.

## Collaboration Model

The PI (Donoho) and the researcher are geographically distributed. Preferred collaboration
mode is a shared `tmux` session on the Mac Pro hub (accessible via Tailscale), so both can
work with the same Claude Code instance simultaneously. Claude Code is installed per-user on
each machine; context travels via this committed memory file and `CLAUDE.md`.

## Requirements Status (R-1 through R-10)

All defined in `docs/VISION.md`. Key decisions:
- **R-9**: At v1.0, EMS injects input parameters into result DataFrames automatically.
  Pre-v1.0, researchers must include params themselves (breaking change at v1.0).
- **R-7 (Dashboard)**: In scope for Phase 2.
- **R-6 (Environment reproducibility)**: Git hash + env spec captured at launch.
- **R-8**: Namespacing by researcher/project is required.
- **R-10**: Experiment dependencies via database (downstream queries upstream table).

## Open Questions (3 remaining)

1. **Experiment registry** — registry of all experiments ever run, queryable by
   researcher/project/date/code version. Linked to notebook presentation and R-6 data.
2. **Failure handling** — default behavior TBD; must be dynamically changeable.
3. **Cost tracking** — cloud compute costs recorded per experiment; funding account
   specified in experiment definition.

## Workflow / Preferences

- Read `docs/VISION.md` fresh at the start of each session before discussing requirements.
- Commit after each meaningful unit of work.
- PI (Donoho) is an active stakeholder; shares doc for review between sessions.
