# US-001: New Researcher Onboarding — BigQuery Access

## Story

As a new researcher joining the Donoho Lab, I want to be onboarded to EMS with access to
the lab's BigQuery database, so that I can run experiments and have my results stored and
queryable without needing to manage cloud credentials or infrastructure myself.

## Acceptance Criteria

1. A lab administrator provisions the researcher's namespace (R-8) in BigQuery —
   e.g., `EMS.<researcher>_<project>`.
2. The researcher receives or is pointed to a GCP service account credentials file scoped
   to their namespace.
3. The researcher can run `do_on_cluster()` with their credentials and have results land
   in the correct namespaced table.
4. The researcher cannot read or write to another researcher's tables.
5. The onboarding process is documented in a repeatable runbook (not tribal knowledge).

## Open Issues

- **Who provisions the namespace?** Currently there is no admin tooling in EMS — it would
  be a manual GCP console operation. EMS may need an admin CLI or script for this.
- **Credential scoping** — the current `get_gbq_credentials()` loads a single lab-wide
  service account key. Per-researcher scoping would require either per-researcher service
  account keys or IAM row-level security in BigQuery.

## Related Requirements

- R-8: Multi-Researcher Support (namespacing)
- R-1: Experiment Definition (versioned, recorded before execution)
- R-4: Storage (BigQuery backend)
