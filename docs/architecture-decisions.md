# Architecture Decisions

This document records every significant architectural choice made during EMS design,
including the options examined and the reasoning behind what was selected and what
was rejected. It is a living record — update it when new decisions are made.

---

## AD-1: Compute Framework — Dask vs. Ray

**Decision date:** 2026-03-27
**Status:** Decided — **Dask**

### Options Examined

**Dask**
A parallel computing library built around the DataFrame and array abstractions familiar
to the scientific Python ecosystem. Workers are coordinated by a scheduler; the Dask
`distributed` library adds a `Client`, `Future`, and `as_completed` API. The scheduler
exposes a live web dashboard (port 8787 by default).

**Ray**
A distributed compute framework built around an Actor model and a remote function API.
Highly performant, with a polished job submission API (`ray job submit --no-wait`),
a web dashboard, and a rich ecosystem (RLlib, Serve, Tune). Ray Jobs natively support
"submit and disconnect" semantics.

### Decision

**Dask chosen.** Ray rejected.

### Rationale

Dask embraces the DataFrame as a primary data management abstraction, which matches
how the data science community already thinks about data. The `dask.dataframe` and
`dask.array` APIs are direct extensions of pandas and NumPy — researchers learn one
mental model that works at both laptop and cluster scale.

Ray's Actor model, while architecturally elegant, introduces an abstraction layer that
is unnecessary for the majority of data analytic practitioners. The overhead of learning
actor-based concurrency provides no benefit for embarrassingly parallel parameter sweeps,
which is EMS's core use case.

Additionally, EMS already has a working Dask integration in production. Switching to Ray
would be a significant rewrite with no functional gain for the current user base.

### Consequences

- `do_on_cluster()` continues to use `client.map()` and `as_completed()`.
- The Dask scheduler dashboard is available as a free live-progress URL while any
  cluster is running. Exposed via Tailscale, it partially satisfies the "check from
  phone" requirement at no cost.
- Persistent job execution (submit and disconnect) requires a separate orchestration
  layer — Dask alone does not solve this. See AD-2.

---

## AD-2: Hub Server — Orchestration and Persistent Job Execution

**Decision date:** 2026-03-27
**Status:** Decided — **Self-hosted Prefect Server on Mac Pro hub**

### Context

A key requirement emerged during Phase 2 planning: researchers must be able to launch
a cluster and submit experiments from the hub server, then **disconnect**. The experiment
must continue running. The researcher must be able to check job status from any device
(phone, laptop) via a URL.

This requirement disqualifies any architecture where the experiment process runs in the
researcher's browser session or local Python environment — a fundamental problem with
the current EMS model, where `do_on_cluster()` is a blocking call in the researcher's
process. The existing tmux workaround (documented in MEMORY.md) confirms the pain.

### Options Examined

**2i2c / Managed JupyterHub**
A managed service that runs JupyterHub on Kubernetes in the lab's cloud account. The
operator (2i2c) handles infrastructure; the lab owns the data. Used by several research
communities (Pangeo, etc.) at scale.

*Rejected:* JupyterHub solves shared notebook execution, not persistent job dispatch.
Kernels die on browser disconnect without special configuration. Solving the persistence
requirement on top of JupyterHub adds the same orchestration layer needed anyway. Also
cloud-hosted — contradicts the Mac Pro hub requirement.

**Hybrid serverless on cloud (AWS/GCP/Azure)**
Notebook execution via SageMaker Studio / Vertex AI Workbench; job APIs via
Lambda / Cloud Functions; dashboard via a managed web service.

*Rejected:* Cold starts make notebook UX poor. Building the experiment registry and
progress dashboard as custom cloud functions adds complexity without reducing it.
High vendor lock-in risk. Not clearly better than a self-hosted solution.

**Self-hosted JupyterHub on Mac Pro**
JupyterHub running directly on the Intel Mac Pro, accessible to the team via Tailscale.
Zero ongoing cost, full control, Python + R kernels.

*Rejected as the primary solution:* JupyterHub's file browser is not a structured
experiment registry. Kernels die on disconnect without special configuration. The
persistent job execution requirement still requires an orchestration layer on top.
Retained as a potential addition for shared notebook analysis if the team needs it —
but not the hub's primary role.

**Posit Workbench (formerly RStudio Workbench)**
Commercial product providing first-class Python and R kernel support in the same
environment, with Posit Connect for dashboard publishing.

*Not selected:* Commercial license cost. R usage in the lab does not yet justify the
investment. Would still require orchestration for persistent jobs.

**Marimo**
A modern reactive notebook format where notebooks are `.py` files (not JSON), making
them version-controllable and reproducible by design. Self-hostable.

*Not selected:* Young ecosystem; R support absent. Risk too high for a production lab
environment. The reproducibility properties are compelling and worth revisiting in a
later phase.

**Custom FastAPI + job queue (Celery/Redis or SQLite-backed)**
A thin web server on the Mac Pro with a persistent job queue. Researcher submits an
experiment via web form; the server runs it as a background worker; a dashboard page
reads from BigQuery.

*Not selected as primary:* Maximum control, minimum dependency, but you build and
maintain the orchestration layer. Failure handling, retry logic, and job state
management are non-trivial. Prefect already solved all of this correctly. The
custom approach remains viable as a fallback if Prefect proves too heavy.

**Coiled (cloud-managed Dask)**
The team already uses Coiled for cloud Dask clusters. Coiled has workspace and
job-submission features.

*Not selected as hub:* Cloud-dependent; Coiled controls the dashboard, not the lab.
Does not cover SLURM or local clusters. Continues in use as a cloud cluster provider.

**Ray (self-hosted)**
Ray's `ray job submit --no-wait` natively solves "submit and disconnect." The Ray
Dashboard is a polished web UI accessible from any device.

*Rejected:* See AD-1. Ray was rejected as the compute framework; adding it solely as
a job runner would introduce the Ray dependency without the compute benefit.

**Prefect Server (self-hosted on Mac Pro)**
Prefect is a Python-native workflow orchestration platform. `prefect server start` runs
on the Mac Pro. Researchers submit Flows via web UI or Python API and disconnect
immediately. The Prefect web dashboard is accessible from any device via Tailscale.
Prefect has first-class Dask integration via `DaskTaskRunner`.

*Selected.* See Decision and Rationale below.

### Decision

**Prefect Server, self-hosted on the Mac Pro hub, with Dask as the task runner.**

### Rationale

Prefect directly satisfies all three hub requirements:

1. **Launch from server** — Flows are submitted to Prefect Server via API or web UI,
   not from the researcher's local machine.
2. **Disconnect** — Flows run as server-side processes; the researcher's browser session
   is irrelevant to execution.
3. **Check via URL** — The Prefect dashboard is a web application accessible from any
   device on Tailscale. Per-flow run history, logs, and status are all visible there.

Prefect + Dask is a natural pairing: Prefect owns the job lifecycle (submission,
persistence, history, failure records), and Dask owns the compute (embarrassingly
parallel dispatch, batched results). Each system does what it does best. The existing
`do_on_cluster()` function maps directly onto a Prefect Flow with minimal changes.

Self-hosting on the Mac Pro satisfies the constraint of no cloud-specific runtime
dependencies and keeps the hub on lab-controlled infrastructure accessible via Tailscale.

Open question 2 (failure handling) is partially resolved by this choice — Prefect
records failed runs with logs and supports retry policies at the Flow level.

### Chosen Architecture

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

Notebook analysis (visualization, hypothesis exploration) runs separately — researchers
connect local Jupyter or R sessions directly to BigQuery. The hub's role is orchestration
and observability, not notebook hosting.

### Consequences

- `do_on_cluster()` must be wrapped as a Prefect Flow. This is additive — the existing
  function signature does not change; the Flow is a thin wrapper.
- Prefect Server becomes a Mac Pro service (systemd unit or launchd plist).
- The experiment registry (open question 1 in VISION.md) can be implemented as Prefect
  Flow metadata + tags, or as a separate BigQuery table. Decision deferred to registry
  design phase.
- The Dask scheduler dashboard (port 8787) is exposed via Tailscale as a secondary
  live-progress URL while clusters are active.
- JupyterHub on the Mac Pro is adopted as the Phase 2 notebook surface layer (see AD-5).
  Its role is researcher interface and analysis, not job execution.

---

## AD-3: Storage Backends

**Decision date:** Pre-v1.0 (established in Phase 1)
**Status:** Decided — **SQLite (local) + PostgreSQL via Cloud SQL + Google BigQuery**

### Rationale

Three backends serve distinct purposes:

- **SQLite** — local durability during computation. Written first; survives cluster
  deallocation. Zero configuration.
- **PostgreSQL via Cloud SQL** — remote relational store for programmatic access and
  multi-researcher queries. Accessed via Cloud SQL Python Connector.
- **BigQuery** — analytical query engine for large result sets. The primary interface
  for the notebook analysis frontend. Researcher queries run here.

BigQuery is the **contract** between the compute backend and the analysis frontend.
All data flows through it; the analysis environment never touches SQLite or PostgreSQL
directly.

### Consequences

- `Databases` class manages all three simultaneously; writes are batched to stay within
  BigQuery / SQLAlchemy row/cell limits.
- The `StorageBackend` abstraction (Phase 2 refactor) will clean up the current 4×
  duplicated if/elif dispatch without changing this decision.

---

## AD-4: Python Version

**Decision date:** 2026-03-27
**Status:** Decided — **Python 3.11 for v1.0; Python 3.12 for v1.1**

### Rationale

Python 3.12 was considered for v1.0. Rejected on timing: the conda-forge ecosystem
for scientific computing (Dask, pandas, Google Cloud libraries) has solid 3.12 support
but 3.13 is not yet ready for production scientific stacks.

Python 3.11 is retained for v1.0.0 to minimize risk during the stability release.
Python 3.12 upgrade is planned as a dedicated v1.1 follow-on, where it can be tested
in isolation against the full dependency chain.

Python 3.13 (free-threaded mode) deferred to late 2025/2026 review — the scientific
ecosystem has not yet shipped production-ready free-threaded wheels.

---

## AD-5: Hub Surface Layer — JupyterHub

**Decision date:** 2026-05-03
**Status:** Decided — **JupyterHub on Mac Pro, Phase 2**

### Context

The Phase 2 hub architecture (AD-2) establishes Prefect as the job orchestration layer
and Dask as the compute engine, but provides no shared, server-side notebook environment.
Researchers need a surface to:

- Find, edit, and version experiment specification notebooks
- Submit experiments to Prefect without maintaining a local Jupyter session
- Run analysis notebooks connected to BigQuery from any device
- Browse the experiment registry alongside their notebooks

Without a shared surface, the notebook-as-spec workflow central to the EMS design
cannot be validated against real researcher behavior.

### Why This Is Different from the AD-2 Rejection

In AD-2, JupyterHub was rejected as the **executor**: the architecture where a kernel
running in JupyterHub calls `do_on_cluster()` and the experiment dies when the browser
disconnects. That rejection stands.

AD-5 adopts JupyterHub as the **surface layer** only. The kernel submits an experiment
to Prefect via a single API call and can immediately die; Prefect owns the persistent
execution. JupyterHub is the researcher's interface; Prefect is the engine.

### Options Examined

**Local Jupyter only (status quo)**
Each researcher runs their own Jupyter session on their laptop or via SSH. No shared
notebook environment; no server-side access from phone or tablet.
*Rejected:* Does not satisfy the "check from any device" requirement for analysis;
creates no shared record of experiment notebooks.

**VS Code Server (code-server)**
A browser-accessible VS Code instance running on the Mac Pro. Full IDE experience;
supports Jupyter notebooks via extension.
*Not selected:* Heavier than needed for notebook-centric workflows; less familiar to
scientific Python community; no native multi-user kernel isolation.

**Marimo**
Reactive notebook format (`.py` files, not JSON); self-hostable; reproducible by
design. Considered in AD-2.
*Not selected:* Young ecosystem; R support absent; risk for a production lab environment.
Worth revisiting in Phase 3 or 4.

**JupyterHub on Mac Pro**
Multi-user JupyterHub running as a `launchd` service on the Mac Pro, accessible via
Tailscale. Each researcher gets an isolated kernel environment. Notebooks are pulled
from git repos on demand; JupyterHub is the interface, not the store.
*Selected.* See Decision and Rationale below.

### Decision

**JupyterHub on Mac Pro as the Phase 2 notebook surface, brought forward from Phase 3.**

### Rationale

**Early validation is the primary reason.** The notebook-as-spec workflow is central
to the EMS Phase 2 design: researchers define experiment dicts in notebooks, submit to
Prefect, and disconnect. If researchers bypass JupyterHub in practice — preferring local
Jupyter and SSH — the Prefect integration design built around that workflow is wrong.
Discovering this in Phase 2 costs an operational setup. Discovering it in Phase 3, after
Prefect integration is complete, is expensive to unwind.

**Operational cost is low.** JupyterHub is a Python package; `launchd` plist deployment
on the Mac Pro takes hours. The incremental cost of adding it to Phase 2 is small
relative to the feedback value.

**Complementary roles, no conflict.** JupyterHub and Prefect solve different problems
and do not overlap. JupyterHub provides the editing and analysis surface; Prefect
provides persistent execution and history. Together they cover the full researcher
workflow without either system doing the other's job.

### Chosen Architecture

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
                                                     ▲
                                                     │ reads
                                             Analysis Notebooks
                                             (running in JupyterHub)
```

### What We Are Measuring

Bringing JupyterHub into Phase 2 is also an instrumented experiment. Success criteria:

1. Researchers open JupyterHub (not SSH to local Jupyter) when starting experiments.
2. The git-repo → JupyterHub pull workflow is smooth enough that notebooks stay
   version-controlled without friction.
3. The `submit_experiment()` notebook cell is the natural entry point for launching
   experiments, not a workaround.
4. Researchers use JupyterHub for BigQuery analysis without needing a local setup.

If criteria 1 or 3 fail, the notebook-as-spec design requires revision before Phase 3.

### Consequences

- JupyterHub is deployed on the Mac Pro as a `launchd` service alongside Prefect Server.
- Notebooks live in researcher project git repos; JupyterHub pulls them on demand.
  JupyterHub is not the notebook store.
- Phase 2 Item 4 is split into three sub-items: 4a (JupyterHub deployment), 4b
  (Prefect integration), 4c (JupyterHub → Prefect submission wiring). 4a and 4b are
  independent and can proceed in parallel; 4c requires both.
- The experiment registry (OQ-6, Item 3) gains a natural browsable surface in JupyterHub
  before a dedicated registry UI is built.
