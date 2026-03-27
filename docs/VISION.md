# Vision & Goals

## Why

Scientific computation experiments are expensive to run, hard to reproduce, and difficult
to monitor across large parameter spaces and distributed clusters. Researchers lose time
re-running work they've already done, lose data when compute nodes are deallocated, and
lack visibility into what's running, what's finished, and what failed.

EMS exists to eliminate that friction: define an experiment once, run it reliably at any
scale, and make results immediately available to analysts — without burdening the researcher
with infrastructure management.

The current `EMS` package (`src/EMS/manager.py`) is the Phase 1 foundation. This document
describes where we are taking it.

---

## Architectural Vision

### Two-System Architecture

EMS is composed of two distinct systems with the SQL database (BigQuery) as the shared
interface between them:

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

### Phase 2 Hub Architecture

The Phase 2 hub is a **Prefect Server running on the lab's Intel Mac Pro**, accessible
to the team via Tailscale. Prefect provides persistent job execution, a web dashboard,
and run history. Dask provides the compute. BigQuery remains the data contract.

```
Researcher (any device, Tailscale)
        │
   ┌────┴─────────────────────┐
   │                          │
   ▼                          ▼
Prefect Server            Dask Dashboard
(job submit / history /   (live cluster view,
 experiment registry)      free while cluster runs)
        │
        │ DaskTaskRunner
        ▼
   Dask Cluster  ────writes────▶  BigQuery / SQLite
   (Sherlock / DGX Spark / GCP)
```

**Key properties of this architecture:**

- Researchers submit experiments from the hub via Prefect UI or Python API, then
  disconnect. Experiments run to completion as server-side Prefect Flows.
- Job status, logs, and history are visible from any device via the Prefect web UI
  (Tailscale URL).
- The Dask scheduler dashboard (port 8787, Tailscale-exposed) provides live cluster
  visibility while a cluster is active.
- Notebook analysis runs separately — researchers connect local Jupyter or R sessions
  directly to BigQuery. The hub is an orchestration and observability layer, not a
  notebook host.
- No cloud-specific runtime dependencies. The hub runs on lab-owned hardware.

For the full record of alternatives considered and rejected, see
`docs/architecture-decisions.md` (AD-2).

### Phased Development

**Phase 1 (complete — v1.0.0 RC):** A working library that enforces a style of
embarrassingly parallel computation. Deduplication, batched writes, multi-backend storage,
Dask cluster dispatch.

**Phase 2 (active):** The Prefect-based hub server. Persistent job execution, experiment
registry, live progress dashboard, scaffolded analysis notebooks, and the common result
utilities (R-11, R-12) researchers currently copy-paste into every project.

**Phase 3:** Select tools and patterns to support the full research team workflow.

**Phase 4:** Transition research outputs into a Frictionlessly Reproducible public server.

---

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

---

## Target Users

- **Researchers** — define and run experiments (parameter sweeps, Monte Carlo simulations)
- **Analysts** — read results and render views (Jupyter, R, Matlab)
- **Lab administrators** — manage infrastructure, credentials, and costs

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
- EMS captures and records the exact code version (git hash) and environment spec at
  experiment launch time.
- Capture must cover **both** EMS version and the research project code version.
- This information is stored in the experiment registry (see open question 1).

### R-7: Dashboard
- A web-based dashboard provides live visibility into in-progress computations.
- Accessible to both researchers and lab staff.
- Serves as both a progress monitor and a record of completed experiments.
- Hosted on the lab hub server (Intel Mac Pro, Tailscale-accessible).

### R-8: Multi-Researcher Support
- EMS enforces namespacing by researcher and/or project to prevent table name collisions
  in shared databases.

### R-9: Result Schema — Parameter Injection
- EMS injects all input parameter keys into every result row before storage.
- Experiment callables need only return computed output values; EMS associates results
  with their parameters automatically.
- **Must handle multi-row returns**: some callables emit multiple rows per parameter
  combination (e.g., one row per iteration). EMS injects input params into every row.
- **Pre-v2.0 (current state):** Researchers must continue to include all input parameters
  in their returned DataFrames. This discipline is required until R-9 lands.

### R-10: Experiment Dependencies
- EMS supports multi-phase workflows where one experiment's outputs feed another's inputs.
- Native `derive_params()` pattern: given an upstream result table and a researcher-supplied
  transformation function, produce a parameter list for a downstream experiment.
- This replaces the painful CSV hand-off between projects observed in practice.

### R-11: Common Result Utilities
- EMS provides first-class utilities shared across all projects:
  - Groupby aggregation of result tables (mean, std across Monte Carlo replicates)
  - Syncing local SQLite results to remote PostgreSQL or BigQuery
  - Exporting result subsets to CSV
- These must not be copy-pasted into every project. Confirmed pattern: identical
  `stack_results.py`, `copy_results_to_cloud.py`, and `write_to_gbq.py` duplicated
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

### 1. Experiment Registry Implementation
Evidence from two researchers confirms this is required, not optional. Both used git
branches (70+ and 30+ respectively) as a substitute for a versioned experiment registry.

The registry must be queryable by researcher, project, date, and code version, and must
link to the scaffolded analysis notebook (R-6, US-003).

**Options under consideration:**
- Embedded DB table (in BigQuery or local SQLite alongside results)
- Structured directory of versioned JSON files with a query layer
- Separate lightweight service

### 2. Failure Handling
Both researchers experienced silent failure drops with no post-mortem data available.
Failed Dask futures are currently logged as warnings and skipped.

**Questions:**
- Should failed instances be re-queued automatically, flagged for manual review, or
  logged and skipped (current behavior)?
- Should there be a default behavior that can be changed per-experiment?
- What post-mortem data should be captured (parameters, exception, traceback)?

### 3. Cost Tracking
Should EMS record cloud compute costs per experiment and report against funding accounts?
The `EMS_Model.md` specifies a `Funding` table and per-experiment cost attribution.

---

## Phase 2 Architecture Prerequisite

Before Phase 2 features can be built, `manager.py` must be refactored:

- **Split into a package**: `__init__.py`, `storage.py`, `cluster.py`, `registry.py`,
  `utils.py` — the current 600-line god module does not scale to Phase 2 scope.
- **`StorageBackend` abstraction**: Replace the 4× duplicated if/elif dispatch chains in
  `read_params()`, `read_table()`, `_push_to_database()` with a clean backend interface.
- **Configurable `record_experiment()` path**: Currently hardcoded to CWD; must be
  configurable so JSON records land in a consistent location.

This refactor is the first work item on `claude-v2.0.0_phase2`.
