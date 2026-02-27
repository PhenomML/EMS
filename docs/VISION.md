# Vision & Goals

## Why

Scientific computation experiments are expensive to run, hard to reproduce, and difficult to monitor across large parameter spaces and distributed clusters. Researchers lose time re-running work they've already done, lose data when compute nodes are deallocated, and lack visibility into what's running, what's finished, and what failed.

EMS exists to eliminate that friction: define an experiment once, run it reliably at any scale, and make results immediately available to analysts — without burdening the researcher with infrastructure management.

The current `EMS` package (`src/EMS/manager.py`) is a working first step. This document describes where we want to take it.

## Architectural Vision and Scenarios

This system is operated by the research lab. To that end, it records the experiments and costs as well as provides the records for reproducibility analyses. To that end, it has three major users -- the PI/lab staff, the individual researcher, and the scientific public interested in Frictionless Reproducibility of results.

Currently, EMS is a library that enforces a style of embarrassingly parallel computation. This phase of development is to create the computational hub for the lab and researcher. To that end, we envision a server of a "tree of notebooks" that encompass everything needed to recreate a computational experiment, github hashes of research code, database tables, dataframe schema, rendering code. Data is to always reside in a separate database. Eventually, tables of this database will be accessible to the public to support published research. In addition to being a record of computation, it will also be a dashboard for in progress computations. This allows both the researcher and lab staff to observe and manage the progress of the computation.

The third phase of the project will encompass selecting tools and patterns to support the research team. The fourth phase will support transitioning research into a Frictionlessly Reproducible server.


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

### R-6: Environment Reproducibility
- EMS captures and records the exact code version (git hash) and environment spec at experiment launch time.
- This information is stored alongside the experiment registry entry (see R-1).

### R-7: Dashboard
- A web-based dashboard provides live visibility into in-progress computations.
- Accessible to both researchers and lab staff.
- Serves as both a progress monitor and a record of completed experiments.

### R-8: Multi-Researcher Support
- EMS enforces namespacing by researcher and/or project to prevent table name collisions in shared databases.

### R-9: Result Schema
- At v1.0, EMS injects all input parameter keys into every result DataFrame before storage. Experiment callables need only return computed values; EMS is responsible for associating results with their parameters.
- **Pre-v1.0 (breaking change notice):** Researchers must continue to include all input parameters in their returned DataFrames. This discipline is required until v1.0 lands and EMS takes over parameter injection.

### R-10: Experiment Dependencies
- EMS supports workflows where one experiment's outputs feed another's inputs.
- This is achieved naturally via the database: a downstream experiment queries an upstream result table as its input.
- Pipeline configuration is flexible, including dynamic querying of prior steps.

---

## Out of Scope

- Rendering / visualization of results (that belongs in researcher notebooks).
- Managing the content or correctness of experiment callables (EMS runs what it's given).
- Real-time streaming of partial results within a single experiment instance.

---

## Open Questions

1. **Experiment registry** — Should EMS maintain a registry of all experiments ever run (not just results), queryable by researcher, project, date, or code version? Notebook presentation and all of the information from R-6.

2. **Failure handling** — How should failed instances be treated? Re-queued automatically, flagged for manual review, or silently dropped? Should have a default behavior. Should have a way to dynamically change that behavior.

3. **Cost tracking** — Should EMS record cloud compute costs per experiment and report against funding accounts? Specified in experiment specification.
