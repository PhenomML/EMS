# Vision & Goals

## Why

Scientific computation experiments are expensive to run, hard to reproduce, and difficult to monitor across large parameter spaces and distributed clusters. Researchers lose time re-running work they've already done, lose data when compute nodes are deallocated, and lack visibility into what's running, what's finished, and what failed.

EMS exists to eliminate that friction: define an experiment once, run it reliably at any scale, and make results immediately available to analysts — without burdening the researcher with infrastructure management.

The current `EMS` package (`src/EMS/manager.py`) is a working first step. This document describes where we want to take it.

## Architectural Vision and Scenarios

This system is operated by the research lab. To that end, it records the experiments and costs as well as provides the records for reproducibility analyses. To that end, it has three major users -- the PI/lab staff, the individual researcher, and the scientific public interested in Frictionless Reproducibility of results.

### Two-System Architecture

EMS is composed of two distinct systems with the SQL database (BigQuery) as the shared interface between them:

**Backend — Compute Engine**
Specifies experiments, deploys them to a cluster, runs them, and writes results into the
SQL database. This is the current EMS library. The researcher interacts with it to define
parameter spaces and launch runs.

**Frontend — Visualization & Analysis**
A notebook-oriented environment (Python or R kernel, researcher's choice) that connects
directly to the SQL database on BigQuery. Researchers query results, form visualizations,
develop hypotheses about unexplored regions of the parameter space, and fit equations to
observed data. This system does not move data — it only reads from the database.

The SQL database is the contract between the two systems. Everything flows through it.

### Phased Development

Currently, EMS is a library that enforces a style of embarrassingly parallel computation.
Phase 2 is to create the computational hub for the lab and researcher: a server of a
"tree of notebooks" encompassing everything needed to recreate a computational experiment —
git hashes of research code, database tables, dataframe schemas, rendering code. Data
always resides in a separate database. Eventually, tables will be accessible to the public
to support published research. The hub also serves as a dashboard for in-progress
computations, allowing both researchers and lab staff to observe and manage progress.

The third phase will select tools and patterns to support the research team. The fourth
phase will support transitioning research into a Frictionlessly Reproducible server.


## Design Principles

- **Make the right thing the default.** Researchers under time pressure will skip optional
  steps. If analysis notebooks, experiment records, and environment capture require extra
  effort, they won't happen. EMS should scaffold them automatically so that doing the right
  thing is easier than not doing it.
- **The database is the contract.** All data lives in the database. The compute backend
  writes; the analysis frontend reads. Nothing important should live only in files or memory.
- **Friction kills science.** Every manual step between completing a run and seeing results
  risks the results never being examined. Minimize steps; automate handoffs.
- **Don't make researchers reinvent utilities.** Aggregation, cloud sync, CSV export, and
  result padding are solved problems that appear in every project. EMS owns them so
  researchers don't copy-paste them.

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
- EMS supports multi-phase workflows where one experiment's outputs feed another's inputs.
- The real pattern observed in practice: run experiment A → extract derived parameters
  (e.g., fit a model to results, extract coefficients) → use those as the input parameter
  grid for experiment B.
- EMS should provide a native `derive_params()` pattern: given an upstream result table
  and a researcher-supplied transformation function, produce a parameter list for a
  downstream experiment. This replaces manual CSV hand-off between projects.

### R-11: Common Result Utilities
- EMS provides first-class utilities shared across all projects:
  - Groupby aggregation of result tables (mean, std across Monte Carlo replicates)
  - Syncing local SQLite results to remote PostgreSQL or BigQuery
  - Exporting result subsets to CSV
- These must not be copy-pasted into every project. Observed in practice: identical
  `stack_results.py`, `copy_results_to_cloud.py`, and `write_to_gbq.py` files duplicated
  across every researcher project.

### R-12: Variable-Length Output Support
- EMS provides a convention or helper for callables that return variable-length arrays
  (e.g., singular values whose count depends on input matrix dimensions).
- Researchers must not be responsible for computing max output dimensions and padding
  results to a fixed DataFrame width manually.

---

## Out of Scope

- Managing the content or correctness of experiment callables (EMS runs what it's given).
- Real-time streaming of partial results within a single experiment instance.
- Authoring the visualization logic itself (researchers write their own notebook cells or
  plotting code; EMS triggers and connects, but does not own the rendering).

---

## Open Questions

1. **Experiment registry** — Evidence from two researchers confirms this is required, not
   optional. Both used git branches (70+ and 30+ respectively) as a substitute for a
   versioned experiment registry. The registry must be queryable by researcher, project,
   date, and code version, and must link to the scaffolded analysis notebook (R-6, US-003).
   The open question is implementation: embedded in EMS, a sidecar database table, or a
   structured directory of versioned JSON files?

2. **Failure handling** — How should failed instances be treated? Re-queued automatically,
   flagged for manual review, or silently dropped? Should have a default behavior and a
   way to dynamically change it. Both researchers experienced silent failure drops with
   no post-mortem data available.

3. **Cost tracking** — Should EMS record cloud compute costs per experiment and report
   against funding accounts? Specified in experiment definition.
