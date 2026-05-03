# Experiment Registry Design

**Date:** 2026-05-03
**Status:** Decision — resolves OQ-6
**Blocks resolved:** Phase 2 Items 4b and 4c (Prefect integration, JupyterHub wiring)
**Related:** `phase2-plan.md` §Item 3, `open-questions.md` OQ-6

---

## Summary

**Decision: JSON directory as the primary registry, with Prefect annotations as a
free secondary surface and BigQuery sync as an optional upgrade path.**

The registry is a directory of JSON files on the Mac Pro hub, one file per experiment
launch. It is browsable from JupyterHub, queryable via pandas, updated by Prefect as
experiments run, and synced to BigQuery when cross-researcher analytical queries are
needed.

---

## Why Not the Alternatives

### BigQuery table (rejected as primary)

BigQuery is the right analytical surface for results, but wrong as the primary registry
store. The blocking problem: BigQuery credentials are required at experiment launch time.
Local experiments — a researcher running `do_on_cluster()` against a local Dask cluster
with SQLite-only storage — have no BigQuery credentials. The registry must work for every
EMS workflow, not just the cloud-connected ones.

BigQuery is the right *eventual* destination for multi-researcher registry queries. It
is reached via the R-11 sync utility (same pattern as SQLite → BigQuery result sync),
not by making it the write target.

### Prefect Flow metadata (rejected as primary)

Prefect's run history and tags give a free registry-like view when Prefect is running,
and the Prefect dashboard is the right surface for "what is running right now." But
Prefect metadata is not durable across Prefect DB resets, not queryable via SQL
without standing up a separate query layer, and not available for experiments that
predate the Prefect integration. It is a useful secondary surface, not the source
of truth.

### Custom SQLite table (considered, not selected)

A `registry` table in `data/EMS.db3` would be locally queryable and zero-dependency.
Rejected because: (1) the registry naturally lives on the hub server, not in each
researcher's local SQLite file; (2) JSON files are git-trackable and human-readable
without tooling; (3) the experiment dict is already JSON-serializable and
`record_experiment()` already writes JSON files — the implementation is already 90%
done.

---

## The Hub Architecture Insight

Phase 2 changes the registry requirements in a fundamental way. In Phase 1 (EMS v1.0),
experiments run in the researcher's local Python process. The registry is per-researcher
and per-machine.

In Phase 2, experiments are submitted to Prefect on the Mac Pro and run there. **All
Phase 2 experiments pass through one machine.** The registry directory on the Mac Pro
is the natural shared record: every experiment lands there, every researcher can read
it via JupyterHub, and Prefect has direct filesystem access to update status.

This eliminates the "not queryable across machines" objection to the JSON directory
option. In Phase 2, there is one machine.

---

## Registry Record Format

Each registry entry is a single JSON file. Its content is:

```json
{
  "run_id":           "a3f7c91e-...",
  "launched_at":      "2026-05-03T14:22:07Z",
  "launched_by":      "adohoho",
  "hostname":         "mac-pro-hub.local",
  "status":           "submitted",

  "ems_version":      "1.0.0",
  "project_git_hash": "d4e7a3f...",

  "design_doc":       "PhenomML/SteinSense:notebooks/sherlock_a100/steinsense_sweep_v1.ipynb",

  "cluster_config": {
    "type": "SLURMCluster",
    "target": "sherlock_a100",
    "n_workers": 8
  },

  "experiment": {
    "table_name":    "steinsense_sweep_v1",
    "callable":      "steinsense.jax_gpu.run_recovery_closed",
    "callable_file": "src/steinsense/jax_gpu.py",
    "params":        [...],
    "fixed_params":  {...}
  }
}
```

The `experiment` key is the full experiment dict verbatim — the v3 format is already
JSON-serializable. No transformation needed.

### Status lifecycle

| Status | Set by | When |
|--------|--------|------|
| `submitted` | EMS at launch | When the Flow is submitted to Prefect |
| `running` | Prefect Flow hook | When the first task executes |
| `completed` | Prefect Flow hook | When `do_on_cluster()` returns normally |
| `failed` | Prefect Flow hook | When the Flow terminates with an exception |

For pre-Prefect experiments (EMS v1.0 runs), status is not tracked — the JSON file
is written at launch with `status: submitted` and never updated. This is acceptable:
the purpose of the registry for historical runs is provenance, not lifecycle tracking.

---

## File Naming Convention

```
data/registry/{YYYY-MM-DD}T{HHMMSS}_{table_name}_{run_id[:8]}.json
```

Example:
```
data/registry/2026-05-03T142207_steinsense_sweep_v1_a3f7c91e.json
```

Properties:
- **Lexicographic sort = chronological order.** A plain `ls` shows history.
- **`table_name` in the name.** Easy to grep for all runs of a study.
- **`run_id` suffix.** Unique; links to the Prefect run URL.
- **Human-readable.** Researchers can open any file and understand it.

---

## Storage Location

The registry directory lives on the Mac Pro hub at a path configurable in EMS settings,
defaulting to the `data/registry/` subdirectory of the EMS data directory.

For Phase 2, `data/registry/` on the Mac Pro is:
- Writable by the Prefect worker process
- Readable by all JupyterHub kernels (shared filesystem)
- Not git-tracked (too large, too volatile — add to `.gitignore`)

For pre-Phase-2 local use, `data/registry/` is local to the researcher's machine.
The file format is identical; the only difference is that the files are not shared.

---

## Query Interface

### Direct pandas (always available)

```python
import glob, json
import pandas as pd

records = []
for path in glob.glob('data/registry/*.json'):
    with open(path) as f:
        rec = json.load(f)
    # Flatten one level for easy querying
    row = {k: v for k, v in rec.items() if k != 'experiment'}
    row.update(rec['experiment'])
    records.append(row)

df = pd.DataFrame(records)

# All runs for the SteinSense study
df[df['table_name'] == 'steinsense_sweep_v1']

# All completed runs on Sherlock
df[(df['status'] == 'completed') &
   (df['cluster_config'].apply(lambda c: c['target']) == 'sherlock_a100')]
```

### EMS registry module (Phase 2 addition)

A thin `EMS.registry` module wraps the glob + flatten pattern:

```python
from EMS.registry import search, load_run

# Search by any top-level or experiment field
results = search(table_name='steinsense_sweep_v1', status='completed')

# Load a specific run record
run = load_run('a3f7c91e')
```

`search()` returns a DataFrame. No new dependencies; just `glob` + `json` + `pandas`.

---

## Prefect Integration Points

When Item 4b (Prefect integration) is implemented, two hooks connect the registry
to Prefect:

**At submission:** `submit_experiment()` writes the JSON file and passes `run_id` to
the Prefect Flow as a parameter. The Prefect run is tagged with `run_id`, `table_name`,
and `callable` so the Prefect dashboard is searchable by experiment identity.

**At completion/failure:** A Prefect Flow post-run hook updates `status` in the JSON
file. The hook receives `run_id` as context and writes one field:

```python
@flow(name="ems-experiment")
def run_experiment(experiment: dict, cluster_config: dict, run_id: str):
    registry.update_status(run_id, 'running')
    try:
        do_on_cluster(experiment, client, db)
        registry.update_status(run_id, 'completed')
    except Exception:
        registry.update_status(run_id, 'failed')
        raise
```

This keeps the registry as the source of truth; Prefect tags are a secondary index.

---

## JupyterHub Surface

Before Item 4b is complete, researchers can browse the registry from JupyterHub using
the pandas interface above. A standard analysis notebook cell in Section 1 of any
experiment notebook:

```python
from EMS.registry import search
search().sort_values('launched_at', ascending=False).head(20)
```

This gives the team a functional registry browser from day one of Item 4a
(JupyterHub deployment), before Prefect is wired up.

---

## BigQuery Sync (Future — R-11)

When multi-researcher analytical queries on registry data are needed, an R-11 utility
syncs the JSON directory to a BigQuery table:

```python
from EMS.utils import sync_registry_to_bigquery
sync_registry_to_bigquery('steinsense_registry_v1')
```

The BigQuery schema mirrors the flattened JSON structure. Sync is idempotent — runs
already in BigQuery are skipped. This is the same pattern as the SQLite → BigQuery
result sync (also R-11).

This upgrade requires no changes to the registry format or the launch path. BigQuery
becomes a queryable mirror, not the source of truth.

---

## `design_doc` Field

The `design_doc` field links each registry entry to the experiment specification
notebook. It is a string in `{repo}:{path}` format:

```
"PhenomML/SteinSense:notebooks/sherlock_a100/steinsense_sweep_v1.ipynb"
```

This is populated by the researcher in the experiment notebook before calling
`submit_experiment()`. It is optional — an empty string if omitted.

In JupyterHub, a registry viewer could turn this into a clickable link to the notebook
on GitHub or to the JupyterHub file browser.

---

## What Changes in the Existing `record_experiment()`

EMS v1.0 already has `record_experiment()`, which writes a timestamped JSON file
containing the experiment dict. Phase 2 extends it minimally:

1. Add the metadata fields (`run_id`, `launched_by`, `hostname`, `ems_version`,
   `project_git_hash`, `cluster_config`, `design_doc`, `status`)
2. Write to `data/registry/` using the naming convention above
3. Return the `run_id` so it can be passed to Prefect

The existing JSON content (the experiment dict) becomes the `experiment` key. No
breaking change to the dict format.

---

## Open Questions Resolved

| OQ | Status |
|----|--------|
| OQ-6 | **Resolved: JSON directory on hub, Prefect annotations, BigQuery sync via R-11.** |
