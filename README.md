# EMS: Experiment Management System

EMS is a Python library for managing large-scale scientific computation experiments
in the [Donoho Lab at Stanford](https://donoho.stanford.edu/). It coordinates parameter
sweeps across Dask clusters (local, SLURM, or Google Cloud) and persists results to
SQLite, PostgreSQL, or Google BigQuery — so researchers can restart interrupted runs
without re-computing completed work.

---

## Installation

### From GitHub (recommended)

```bash
conda env create -f environment.yml
conda activate EMS
```

`environment.yml` pins the package via:

```yaml
pip:
  - git+https://github.com/PhenomML/EMS.git@v1.0.0
```

### Editable install for development

```bash
git clone https://github.com/PhenomML/EMS.git
cd EMS
conda env create -f environment.yml
conda activate EMS
pip install -e .
```

---

## Quick Start

```python
from dask.distributed import LocalCluster, Client
from EMS.manager import do_on_cluster

# Define your experiment callable
def my_experiment(n, mc, method):
    import numpy as np
    result = np.random.randn(n).mean()
    return pd.DataFrame([{'n': n, 'mc': mc, 'method': method, 'result': result}])

# Define the parameter grid
experiment = {
    'table_name': 'my_results',
    'params': [
        {'n': [100, 1000], 'mc': list(range(10)), 'method': ['ols', 'ridge']},
    ],
}

# Run on a local cluster
cluster = LocalCluster()
client = Client(cluster)
do_on_cluster(experiment, my_experiment, client)
```

Results are written to `data/EMS.db3` (SQLite) by default. Re-running
`do_on_cluster()` with the same experiment dict will automatically skip
already-computed parameter combinations.

---

## Experiment Dict Format

| Key | Type | Description |
|-----|------|-------------|
| `table_name` | `str` | **Required.** Destination table / BigQuery table name. |
| `params` | `list[dict]` | List of parameter dicts. Each dict maps param names to lists of values; the Cartesian product is computed per dict and all results are concatenated. |
| `multi_res` | `list[dict]` | Alias for `params`. |
| `parameters` | `dict` | Single parameter dict (no list wrapper). Mutually exclusive with `params`/`multi_res`. |
| `stop_list` | `list[dict]` | Optional. Parameter combinations to unconditionally skip (e.g., known-bad configs). |

**Example with multiple parameter blocks:**

```python
experiment = {
    'table_name': 'sweep_results',
    'params': [
        {'n': [100, 500],        'method': ['ols'],   'reg': [0.0]},
        {'n': [100, 500, 1000],  'method': ['ridge'],  'reg': [0.01, 0.1, 1.0]},
    ],
    'stop_list': [{'n': 100, 'method': 'ridge', 'reg': 1.0}],
}
```

---

## Storage Backends

EMS writes to all configured backends simultaneously.

### Local SQLite (default)

No configuration needed. Database file is created at `data/EMS.db3` relative
to the working directory.

To disable local storage, pass `local_db=False` to `Databases()` or use
the `do_on_cluster()` path without a local DB.

### PostgreSQL via Cloud SQL Proxy

Set the following environment variables:

```bash
export POSTGRES_CONNECTION_NAME="project:region:instance"
export POSTGRES_USER="my_user"
export POSTGRES_PASS="my_password"
export POSTGRES_DB="my_database"
```

Then pass a remote engine:

```python
from EMS.manager import active_remote_engine, do_on_cluster

remote, _ = active_remote_engine()
do_on_cluster(experiment, my_experiment, client, remote=remote)
```

### Google BigQuery

```python
from EMS.manager import get_gbq_credentials, do_on_cluster

credentials = get_gbq_credentials()          # reads ~/.config/gcloud/<key>.json
do_on_cluster(experiment, my_experiment, client, credentials=credentials)
```

Alternatively, pass `project_id=` for application-default credentials.

---

## API Reference

### Main Orchestration

| Function | Description |
|----------|-------------|
| `do_on_cluster(experiment, instance, client, ...)` | Main entry point. Expands params, deduplicates, dispatches, collects. |
| `do_experiment(instance, parameters, db, client)` | Lower-level dispatch; used internally by `do_on_cluster`. |

### Parameter Utilities

| Function | Description |
|----------|-------------|
| `unroll_parameters_gpt(parameters)` | Expand a parameter dict into a flat list via Cartesian product. |
| `unroll_experiment(experiment)` | Expand an experiment dict into a flat parameter list. |
| `remove_stop_list(unrolled, stop)` | Filter out parameter combos in the stop list. |
| `dedup_experiment(df, params)` | Remove combos already present in a DataFrame. |
| `dedup_experiment_from_db(experiment, ...)` | Query the DB and return un-computed combos. |
| `record_experiment(experiment)` | Write a timestamped JSON snapshot of the experiment dict. |

### Storage

| Class / Function | Description |
|-----------------|-------------|
| `Databases(table_name, ...)` | Manages buffered writes to SQLite / PostgreSQL / BigQuery. |
| `create_remote_connection_engine()` | Create a Cloud SQL PostgreSQL engine from env vars. |
| `active_remote_engine()` | Create and validate a remote engine. |
| `get_gbq_credentials(cred_name)` | Load GCP service-account credentials. |

### Cluster Evaluation

| Class | Description |
|-------|-------------|
| `EvalOnCluster(client, ...)` | Dispatch callables and collect results iteratively or in batches. |

### Utilities

| Function | Description |
|----------|-------------|
| `on_worker()` | Returns `True` if the current code is running on a Dask worker. |
| `get_dataset(key)` | Retrieve a named dataset from the Dask scheduler. |
| `read_json(fn)` / `write_json(d, fn)` | JSON serialization helpers. |

---

## Known Limitations

- **No parameter injection (R-9):** Parameter values are not sanitized before being
  passed to worker callables. Do not run untrusted experiment dicts. This will be
  addressed in v2.
- **`record_experiment()` writes to CWD:** The timestamped JSON snapshot is always
  written to the process current working directory, which may not be the project root
  when running on a SLURM cluster or via Coiled. An experiment registry is planned
  for Phase 2.
- **No failure retry logic:** If a Dask future fails, the result is logged as a
  warning and skipped. There is no automatic retry. Check worker logs for details.
- **No experiment registry:** Experiments are tracked only by their JSON snapshot
  files and the database table. A structured registry is planned for Phase 2.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `POSTGRES_CONNECTION_NAME` | Cloud SQL instance connection name (`project:region:instance`) |
| `POSTGRES_USER` | PostgreSQL user |
| `POSTGRES_PASS` | PostgreSQL password |
| `POSTGRES_DB` | PostgreSQL database name |

---

## Citation

If you use EMS in published research, please cite the repository:

```
Andrew W. Donoho. EMS: Experiment Management System. 2024.
https://github.com/PhenomML/EMS
```
