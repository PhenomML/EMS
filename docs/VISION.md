# Vision & Goals

## Why

Scientific computation experiments are expensive to run, hard to reproduce, and difficult to monitor across large parameter spaces and distributed clusters. Researchers lose time re-running work they've already done, lose data when compute nodes are deallocated, and lack visibility into what's running, what's finished, and what failed.

EMS exists to eliminate that friction: define an experiment once, run it reliably at any scale, and make results immediately available to analysts — without burdening the researcher with infrastructure management.

The current `EMS` package (`src/EMS/manager.py`) is a working first step. This document describes where we want to take it.

## Target Users

- **Researchers** who define and run experiments (parameter sweeps, Monte Carlo simulations, etc.)
- **Analysts** who read results and render views (Jupyter, R, Matlab)
- **Lab administrators** who manage infrastructure, credentials, and costs

---

## Requirements

### R-1: Experiment Definition
- Experiments are defined as structured documents (currently Python dicts / JSON).
- Supports multi-resolution parameter blocks (`params`, `multi_res`) and stop lists.
- Experiment definitions are versioned and recorded before execution begins.

### R-2: Parameter Management
- Full Cartesian product expansion across parameter axes.
- Deduplication against previously computed results before any work is dispatched.
- Resume-ability: a re-submitted experiment picks up where it left off.

### R-3: Execution
- Supports local execution (laptop/workstation via Dask `LocalCluster`).
- Supports SLURM-based HPC clusters (Stanford Sherlock, etc.).
- Supports cloud compute (GCP, AWS).
- Embarrassingly parallel dispatch; each unit of work is stateless.

### R-4: Storage
- Results written to local SQLite for durability during computation.
- Results mirrored to remote PostgreSQL (Cloud SQL) and/or Google BigQuery.
- Write batching to stay within database row/cell limits.

### R-5: Observability
- Researchers can see live progress of computation from a notebook or terminal.
- Logging of count, elapsed time, seconds-per-instance, and estimated remaining time.

---

## Out of Scope

- Rendering / visualization of results (that belongs in researcher notebooks).
- Managing the content or correctness of experiment callables (EMS runs what it's given).
- Real-time streaming of partial results within a single experiment instance.

---

## Open Questions

1. **Experiment registry** — Should EMS maintain a registry of all experiments ever run (not just results), queryable by researcher, project, date, or code version?

2. **Failure handling** — How should failed instances be treated? Re-queued automatically, flagged for manual review, or silently dropped?

3. **Environment reproducibility** — Should EMS capture and record the exact code version (git hash) and environment spec at experiment launch time?

4. **Multi-researcher support** — Should EMS enforce namespacing by researcher/project to prevent table name collisions in shared databases?

5. **UI / dashboard** — Is a web-based progress dashboard (beyond log output) in scope?

6. **Cost tracking** — Should EMS record cloud compute costs per experiment and report against funding accounts?

7. **Result schema** — Should EMS enforce or validate a schema for result DataFrames, or remain fully schema-free?

8. **Dependency between experiments** — Should EMS support workflows where one experiment's outputs are another's inputs?
