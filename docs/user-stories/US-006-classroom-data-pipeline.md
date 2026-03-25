# US-006: Classroom Data Pipeline — Bluesky Archive as a Teaching Dataset

## Source

Review of BSky2GBQ project, 2026-03-25.
Classification: Nice-to-have application use case; does not source new EMS requirements
but validates existing design choices and suggests one new capability.

## Context

The Texas Bluesky Archive captures 4.5–5 million posts per day from the Bluesky social
media firehose and persists them to Google BigQuery. Stanford and Columbia classes have
already used this archive for pedagogical purposes. The data is available to researchers
and students via a published cost-plus model that supports Frictionless Reproducibility:
queries are published as supplemental material so any peer can reproduce the exact
dataset used.

The archive is currently operated as a standalone pipeline (BSky2GBQ) using EMS's
`EvalOnCluster` API with `local_db=False` to write directly to BigQuery. It is not
integrated with EMS's experiment management features.

## Story

As a course instructor at Stanford or Columbia, I want to assign students a research
question that can be answered by querying the Bluesky archive on BigQuery, running
computational experiments against that data using EMS, and submitting their analysis
notebook — so that the full workflow from raw social media data to reproducible result
is taught as a single integrated practice.

## What This Looks Like in Practice

1. **Instructor** defines a course dataset query (e.g., "all English-language posts
   containing keyword X between dates A and B") and publishes it as a named BigQuery
   table in the course namespace.
2. **Student** defines an EMS experiment that reads from that table as input parameters
   and runs a computational analysis (sentiment scoring, topic modeling, time-series
   analysis, etc.) across a parameter sweep.
3. EMS dispatches the experiment to a local or shared cluster, writes results to a
   namespaced student table in BigQuery.
4. The scaffolded analysis notebook (US-003) pre-connects to the student's result table;
   the student opens it and begins analysis immediately.
5. **Submission** includes: the experiment definition, the result table query, and the
   analysis notebook — everything needed for a peer to reproduce the result.

## Why This Is a Nice-To-Have

- The archive already works and classes already use it without EMS integration.
- The integration adds pedagogical value (students learn the full EMS workflow) but is
  not required for the archive to function.
- This use case does not require new EMS capabilities beyond what is already planned —
  it exercises R-8 (namespacing), R-9 (parameter injection), US-003 (scaffolded
  notebook), and the BigQuery frontend.

## One New Capability Suggested

**Instructor-defined shared datasets**: A mechanism for an instructor (or lab admin) to
register a named, read-only BigQuery table as a shared input dataset accessible to all
students in a course namespace. Students reference it by name in their experiment
definitions without needing to know the underlying query or credentials.

This is a lightweight extension of R-8 (namespacing) and R-10 (experiment dependencies)
and would also be useful for lab-wide shared reference datasets in research contexts.

## EMS Design Choices Validated

- **`local_db=False`**: The archive writes 4.5–5M rows/day directly to BigQuery with no
  local SQLite. Confirms this must remain a first-class supported configuration.
- **`EvalOnCluster` async API**: The pipeline uses `eval_params_list()` + `next_batch()`
  + `final_push()` for streaming ingestion. Confirms both the simple (`do_on_cluster`)
  and advanced (`EvalOnCluster`) APIs serve distinct real use cases.
- **Frictionless Reproducibility**: The archive's published-query model is a direct
  instantiation of the lab's FR philosophy. EMS's experiment registry (open question 1)
  and R-6 (environment capture) are the research-side complement to this.

## Related Requirements

- R-8: Multi-Researcher Support (student namespacing)
- R-9: Parameter injection
- R-10: Experiment dependencies (course dataset as upstream input)
- US-003: Scaffolded analysis notebook (student submission artifact)
- Open question 1: Experiment registry (published queries as supplemental material)
