# US-002: Experiment Visualization — Reducing Friction from Run to Insight

## Source

Transcript: PI discussion, 2026-03-15.

## Story

As a researcher running a sequence of experiments on a project, I want results to be
automatically visualized when a run completes, so that I never have to manually query
the database to see what I got — because experiments that require manual steps to
visualize often never get looked at.

## Context and Concepts

### Key Constructs

- **Project** — a computational engine (Python) with ~10 named hyperparameters, associated
  with a sequence of experiments and a result schema.
- **Run** — one invocation of EMS dispatching a set of parameter combinations to the engine.
- **Sequence of experiments** — the full history of runs associated with a project. May be
  planned in advance or discovered organically by interacting with results. A sequence spans
  one or more runs; runs can add new parameter combinations as understanding evolves.
- **Engine versioning** — the computational engine may change between runs in an
  upward-compatible way. EMS must track which engine version produced which results.

### Critical Insight

> "A lot of experiments never even get looked at" when visualization requires manual steps.

Visualization is not an optional add-on — it is a first-class part of the experiment
lifecycle. Every extra step between run completion and seeing results reduces the value
of the system.

## Acceptance Criteria

### Post-Run Visualization (R-7 extension)
1. A researcher can attach a **visualization spec** to an experiment definition — specifying
   which columns from the result table to plot, and any subsetting/filtering logic.
2. When a run completes, EMS automatically fires the visualization without any manual
   intervention.
3. The visualization spec is stored alongside the experiment record (versioned, R-1).

### In-Progress Visualization (R-5 / R-7)
4. While a run is executing, a researcher can see:
   - Which regions of the parameter space have been visited.
   - Which have not yet been visited.
   - Which instances failed, with their input parameters exposed.
   - A handle (serial number or ID) for each failure that can be used to access the
     associated log.

### Result Schema (R-9)
5. Every row in the result table includes all input hyperparameters as columns, as well
   as the computed observables. (See R-9: EMS injects parameters automatically at v1.0.)

## Open Issues

- **Visualization spec language** — what form does the spec take? A Python callable?
  A declarative dict? A Vega-Lite spec? Needs decision.
- **Where does visualization render?** — in a notebook, a standalone HTML file, the
  Phase 2 dashboard (R-7), or all of the above?
- **Engine versioning** — how is "upward-compatible engine change" represented? Git hash
  (R-6) is necessary but may not be sufficient; schema changes need handling too.
- **Sequence identity** — is a "sequence of experiments" a first-class EMS object, or
  just a convention (same table name across runs)?

## Related Requirements

- R-1: Experiment Definition (versioned, recorded before execution)
- R-5: Observability (live progress)
- R-6: Environment Reproducibility (engine versioning via git hash)
- R-7: Dashboard (post-run and in-progress visualization)
- R-9: Result Schema (hyperparameters injected into every result row)
