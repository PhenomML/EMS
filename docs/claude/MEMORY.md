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
| `docs/VISION.md` | Requirements R-1–R-12, chosen architecture, phased plan. |
| `docs/architecture-decisions.md` | AD-1 through AD-5 with full rationale and alternatives. |
| `docs/design/phase2-plan.md` | Overall Phase 2 architecture and work items. **Read this.** |
| `docs/design/open-questions.md` | 11 open questions, living tracker. Update here when resolved. |
| `docs/design/notebook-prototype-v3.md` | Current experiment notebook spec (callable in dict, CELLS pattern). |
| `docs/design/implementation-paper-proposal-v7-xla-tpu.md` | SteinSense paper — primary EMS validation challenge. |
| `docs/design/steinsense-repo-brief.md` | Briefing for SteinSense Claude instance creating that repo. |
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

## Architecture Decisions (AD-1 through AD-5)

**AD-1: Dask over Ray.** DataFrame-first culture; Actor model unnecessary for sweeps.

**AD-2: Prefect Server on Mac Pro.** Researcher submits → disconnects → checks URL.
Dask owns compute; Prefect owns lifecycle; BigQuery is data contract.

**AD-3: Storage.** SQLite (local) + PostgreSQL (relational) + BigQuery (analytical).
BigQuery is the contract between compute and analysis. Primary store for multi-cluster work.

**AD-4: Python 3.11 for v1.0; 3.12 for v1.1.** 3.13 deferred.

**AD-5: JupyterHub on Mac Pro as Phase 2 notebook surface.** Moved from Phase 3 for early
validation. Role: researcher edits notebooks, submits to Prefect, runs BigQuery analysis
from any device. Notebooks live in git repos; JupyterHub is the interface, not the store.
Success criteria: researchers open JupyterHub naturally (not SSH to local Jupyter).

Full hub architecture:
```
Researcher (any device, Tailscale)
        │
   ┌────┼─────────────────────────────┐
   │    │                             │
   ▼    ▼                             ▼
JupyterHub              Prefect Server           Dask Dashboard
(edit / submit /        (job execution /         (live cluster view)
 analysis)               history / registry)
        │                DaskTaskRunner
        │ submit_experiment()   │
        └──────────────▶  Dask Cluster ──writes──▶  BigQuery / SQLite
```

---

## Experiment Dict Design (v3 — current)

Key fields added in Phase 2 design:
- `callable`: fully-qualified module path — encodes algorithm/implementation identity
- `callable_file`: path to .py file — enables `upload_file()` and file-level git tracking
- `params`: pure scientific variables only (N, B, δ, distribution, seed)
- `fixed_params`: implementation, jacobian, hardware, algorithm hyperparameters
- CELLS pattern: one dict per (implementation × jacobian) cell; all share `table_name`

Design principle: **callable name IS the implementation identifier**. No generic
dispatch functions; no `implementation` string parameter inside the callable.

---

## Phase 2 — Work Items (updated 2026-05-03)

### 0. Package Refactor (prerequisite — do first)
Split `manager.py` into `storage.py`, `cluster.py`, `registry.py`, `utils.py`.
`StorageBackend` abstraction replaces 4× if/elif dispatch chains.

### 1. R-9: Parameter Injection
EMS injects `{**swept_params, **fixed_params}` into every result row automatically.
Must handle multi-row returns as a first-class case (Apratim's per-iteration trace is
the design driver). Implementation: inject into all rows regardless of count; single-row
is just len=1. API contract open as OQ-4b. For batched MC dispatch (OQ-12), R-9 injects
the `mc` batch key element-wise (one value per row) and all other params as scalars.

### 2. R-6: Git Hash Capture
Capture research project git hash at launch. **OQ-7 resolved: per-row** — `project_git_hash`
in every result row, not registry only. Bug fixes mid-run mean multiple git versions
can coexist in one table; per-row is the only safe audit trail.

### 3. Experiment Registry (OQ-6 — decision pending)
Queryable record: researcher, project, date, git hash, callable, linked notebook.
Options: BigQuery table / JSON directory / Prefect Flow metadata.
Must resolve before Items 4b/4c.

### 4a. JupyterHub Deployment (independent)
Install on Mac Pro as `launchd` service. Multi-user Tailscale access. Git-pull notebooks.
Can start after Item 0.

### 4b. Prefect Integration (independent of 4a)
Wrap `do_on_cluster()` as Prefect Flow. `launchd` service on Mac Pro.
Requires Items 0–3 complete.

### 4c. JupyterHub → Prefect Wiring (requires 4a + 4b)
`submit_experiment()` from notebook cell. End-to-end fire-and-forget validation.

### 5–7. R-11, R-12, R-10
Common utilities, variable-length output helper, `derive_params()`.

---

## SteinSense Repo

- Brief at `docs/design/steinsense-repo-brief.md` — handed to SteinSense Claude instance
- Structure: `src/steinsense/{numpy,jax_cpu,jax_gpu,pytorch_gpu,cupy,triton,cutile}.py`
- Each file: `run_recovery_ad`, `run_recovery_closed` (two entry points per backend)
- **OQ-4a resolved**: `run_recovery_*` returns single-row. Full schema in `steinsense-results-schema.md`.
- EMS v1.0 compat: temporary notebook wrapper adds params to rows until R-9 lands
- **RNG convention (OQ-13 partially resolved)**: problem generation always uses
  `numpy.default_rng`; JAX PRNG is a frozen test fixture only. EMS owns `mc` convention
  and stability requirement; callable owns seed derivation formula.

---

## SteinSense Results Schema (`docs/design/steinsense-results-schema.md`)

Written 2026-05-03, updated 2026-05-04. Resolves OQ-4a and OQ-7. Key decisions:
- **Single-row output** for `run_recovery_*` (OQ-4a)
- **Per-row git hash** `project_git_hash` (OQ-7)
- **`mc` not `seed`** — MC replicate index; matches Apratim's BigQuery schema; callable
  derives seed_val internally; seed_val never stored or injected by EMS
- Full column set: output (wall_time, n_iterations, recovered, final_error) + params
  (N, B, delta, distribution, mc, implementation, jacobian, hardware, max_iterations,
  tolerance) + provenance (project_git_hash, ems_version)
- BigQuery: partition by `hardware`, cluster by `implementation`, `jacobian`, `N`
- **OQ-4b still open**: R-9 multi-row API contract. Apratim's per-iteration trace is
  first-class. Validate return structure before closing.

---

## EMS Issue #12 — Batched MC Dispatch (OQ-12)

SteinSense Claude filed issue #12 (2026-05-04). GPU 2-3.6× slower than CPU for B=5
single-problem dispatch — matmul too narrow for tensor cores. Fix: batch K MC replicates
with same geometry into one dispatch. Effective width = K×B.

Proposed design:
- `batch_key: "mc"` in experiment dict; `batch_size` in `cluster_config`
- Dedup at individual (N, B, delta, mc) level; EMS groups post-dedup by geometry
- Callable receives `mc: list[int]`; returns K-row DataFrame (output cols only)
- Problem generation: numpy loop over mc values (negligible); vmap covers computation
- R-9: scalar params broadcast to all rows; `mc` injected element-wise
- Design document needed: `batch-dispatch-design.md`

---

## Design Agenda (next docs to produce)

1. ~~`steinsense-results-schema.md`~~ — **done** 2026-05-03
2. `progress-visualization.md` — resolves OQ-8
3. `experiment-registry-design.md` — resolves OQ-6; blocks Items 4b/4c
4. `multi-cluster-coordination.md` — cluster routing design for Item 4b

---

## Model & Review Strategy

- Sonnet 4.6 for design and implementation (well-scoped, document-driven work)
- Adversarial critique from Gemini/Codex at key decision points
- Give other models specific bounded questions, not open-ended reviews
- Gemini already corrected the SteinSense Onsager lemma proof

---

## Workflow / Preferences

- Read `docs/VISION.md`, `docs/architecture-decisions.md`, `docs/design/phase2-plan.md`
  at session start.
- Commit after each meaningful unit; push immediately.
- Design docs → `docs/design/`. Open questions → `docs/design/open-questions.md`.
- New architectural choices → new AD entry in `docs/architecture-decisions.md`.
- Notebook prototypes → `notebooks/prototypes/`; template → `notebooks/template/`.
- Concise, direct responses preferred.
- Explicit file versioning (v1, v2, v3) until user is comfortable with git-only versioning.
