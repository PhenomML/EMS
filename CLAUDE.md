# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EMS (Experiment Management System) is a Python package built for the Stanford Donoho Lab to manage large-scale scientific computation experiments. It coordinates parameter sweeps across Dask clusters (local, SLURM, or Google Cloud) and persists results to SQLite (local), PostgreSQL (remote via Cloud SQL Proxy), or Google BigQuery.

## Installation & Environment

```bash
# Create and activate the conda environment
conda env create -f environment.yml
conda activate EMS

# Install the package in editable mode for development
pip install -e .
```

## Common Commands

```bash
# Build the distributable package
python -m build

# Run an example experiment locally
python experiment.py

# Deduplicate an experiment against the database
python dedup_experiment.py

# Copy local SQLite DB to Google BigQuery
python copy_local_db_to_cloud.py

# Copy a table to CSV
python copy_local_db_to_csv.py

# Copy a CSV file to Google BigQuery
python copy_csv_to_cloud.py -t <table_name> -f <file.csv>
```

There is no test suite. The `experiment.py` script in the project root serves as an integration example.

## Architecture

All library code lives in a single module: `src/EMS/manager.py`.

### Core Abstractions

**`Databases`** — manages writing DataFrames to one or more backends simultaneously:
- Local SQLite at `data/EMS.db3`
- Remote PostgreSQL via Cloud SQL (SQLAlchemy engine)
- Google BigQuery via `pandas-gbq`

It batches writes using an in-memory `results` list, flushing when the accumulated DataFrame exceeds `NUM_CELLS` (200k cells) or a time `period` has elapsed. Key methods: `push()`, `batch_result()`, `push_batch()`, `final_push()`, `read_table()`, `read_params()`.

**`EvalOnCluster`** — wraps a Dask `Client` for dispatching experiment callables. Supports sync iteration, async iteration, and `next_batch()` for non-blocking batched collection. Each result is pushed to the `Databases` instance, then the future is released to free cluster memory.

### Experiment Workflow

An experiment is expressed as a Python dict:
```python
experiment = {
    'table_name': 'my_experiment_table',
    'params': [{'param_a': [1, 2], 'param_b': [10, 20]}],  # or 'parameters' / 'multi_res'
    'stop_list': [...]  # optional: param combos to skip
}
```

The main orchestration function is `do_on_cluster()`:
1. `unroll_experiment()` → expands param grid into a flat list of `{key: value}` dicts using `unroll_parameters_gpt()` (Cartesian product via `itertools.product`)
2. `db.read_params()` → queries the DB for already-computed parameter combos
3. `dedup_experiment()` → filters out completed combos
4. `random.shuffle()` → randomizes order (reduces contention / biases)
5. `do_experiment()` → dispatches via `client.map()`, collects in batches, writes results

`record_experiment()` serializes the experiment dict to a timestamped JSON file before running.

### Utility Functions

- `unroll_parameters()` — original parameter unroller (less efficient, kept for reference)
- `unroll_parameters_gpt()` — preferred; uses `itertools.product`
- `remove_stop_list()` — filters a parameter list against a stop list of completed/excluded combos
- `dedup_experiment_from_db()` — standalone helper to get remaining params from a DB
- `get_dataset()` / `on_worker()` — utilities for accessing Dask shared datasets from workers
- `create_remote_connection_engine()` / `active_remote_engine()` — Cloud SQL PostgreSQL connection via environment variables
- `get_gbq_credentials()` — loads GCP service account credentials from `~/.config/gcloud/`

### Remote Database Environment Variables

To use the PostgreSQL backend, set:
```
POSTGRES_CONNECTION_NAME
POSTGRES_USER
POSTGRES_PASS
POSTGRES_DB
```

GBQ credentials file defaults to `~/.config/gcloud/hs-deep-lab-donoho-3d5cf4ffa2f7.json`.

### Size Management

`NUM_CELLS = 200_000` (200 rows × 1,000 columns) is the threshold for splitting writes into chunks. `_write_size_check()` and `_df_size_check()` guard against oversized SQLAlchemy `to_sql()` calls by halving the chunk size when the limit is exceeded.
