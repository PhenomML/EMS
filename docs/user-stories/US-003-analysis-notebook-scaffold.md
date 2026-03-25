# US-003: Analysis Notebook — Scaffolded by Default

## Source

Observation from AMP_matrix_recovery project review, 2026-03-25.
PI guidance: the system should structurally encourage notebooks, not merely permit them.

## Context

In the AMP_matrix_recovery project, the researcher ran 14 experiment scripts, generated
116 JSON files, and computed thousands of parameter combinations across SLURM and cloud
clusters — but kept no analysis notebooks in the project. The PI urged him to do so;
he did not. The friction of creating a notebook from scratch, connecting it to the
database, and writing boilerplate query code was enough to prevent it.

**Design principle**: The right behavior should be the default path. EMS should make it
easier to have an analysis notebook than not to have one.

## Story

As a researcher starting a new experiment project, I want EMS to scaffold an analysis
notebook for me automatically, so that querying and visualizing my results requires
no setup — I just open the notebook and start exploring.

## Acceptance Criteria

1. When a researcher creates a new EMS project (or runs their first experiment), EMS
   generates a project directory containing:
   - The experiment definition file(s)
   - A pre-populated **analysis notebook** connected to the project's result table
2. The scaffolded notebook includes:
   - Boilerplate to connect to the correct database (SQLite locally, BigQuery remotely)
   - A query that loads the result table into a DataFrame
   - A summary display (shape, column names, sample rows) so the researcher can
     immediately see what they have
3. The notebook is named and located consistently — e.g., `analysis/<table_name>.ipynb`
   — so it is always findable.
4. The notebook is versioned alongside the experiment definition in git, not ignored.
5. After each run completes, EMS reminds the researcher (via log output) where their
   analysis notebook is.

## Design Note

The scaffolded notebook is a starting point, not a finished product. The researcher
fills in their visualization and analysis code. EMS's job is to eliminate the blank-page
problem and the setup friction — the first cell should already work.

This directly addresses the observed failure mode: experiments that are computed but
never analyzed because the path from database to insight requires too many manual steps.

## Related Requirements

- R-1: Experiment Definition (notebook is part of the project record)
- R-5: Observability
- R-7: Dashboard (notebook is the researcher-facing front-end of the two-system architecture)
- US-002: Post-run visualization (notebook is the natural host for the visualization spec)
