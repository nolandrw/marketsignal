# Security boundaries

This project has no human sign-in, cookies, passwords, sessions, or visitor JWTs.
The public-facing output is intended to be static and read-only.

## Authentication and authorization

| Boundary | Mechanism | Code/config |
| --- | --- | --- |
| Collector -> Gamma API | No credential (public, read-only HTTPS) | `marketsignal/gamma.py` |
| Local development -> SQLite | Operating-system file permissions | `marketsignal/storage.py` |
| Collector -> PostgreSQL | Restricted SQL role via `DATABASE_URL` | `marketsignal/postgres.py` |
| Migration -> PostgreSQL | Privileged role for `init-db`, never used by a scheduled worker | `marketsignal/cli.py` |
| Cloud Scheduler -> Cloud Run Job | OAuth service-account token, job-scoped `roles/run.invoker` | `scripts/enable_schedule_gcp.sh` |
| Cloud Run -> Secret Manager | Managed workload identity, secret-scoped accessor grant | `scripts/deploy_gcp.sh` |
| CI -> GitHub | Ephemeral checkout credential, read-only and not persisted | `.github/workflows/ci.yml` |
| Future model calls | Server-side API credential, not yet implemented | Planned |

The `yes_token_id` in market records is a public Polymarket outcome identifier,
**not** an access token. No wallet or Polymarket trading permissions are used.

## Secret-handling rules

1. Never commit `.env`, connection URIs, access keys, OAuth tokens, service-
   account JSON keys, or Supabase service-role secrets.
2. Cloud Run references a versioned Secret Manager value and receives it at
   instance startup. The Cloud Scheduler account only invokes the job; it
   cannot read the database secret. Google service-account keys are not used.
3. `REQUIRE_PERSISTENT_DB=1` makes a missing `DATABASE_URL` a hard failure.
4. Routine jobs do not execute DDL. Set up schema with `init-db` and the
   one-time migration credential, then use the restricted SQL role.
5. Unexpected exception *messages* are not copied to persistent run audit
   records or shared logs, because they might contain connection details.
6. Do not expose the PostgreSQL connection URI, database table endpoints, or
   Supabase service key to the browser. A future publisher must create a
   validated, public-data-only projection.

## Untrusted content and agent boundaries

Market titles, articles, URLs and retrieved pages are data, not instructions.
No model currently executes in this repository. Future agents must not receive
raw credentials or have direct publishing rights: deterministic authorization
and independent factual checks must precede any publication operation.

## Threats and unresolved controls

- **Credential leakage:** use Secret Manager, least-privilege principals,
  secret rotation and scrubbed error logs. Live credentials are not stored here.
- **Duplicate execution:** bucketed snapshots and unique signal constraints
  make retries idempotent. Scheduled executions should be monitored for overlap.
- **Source integrity:** Gamma metadata may change; collect raw timestamps,
  retain source references and avoid interpreting market prices as facts.
- **Publishing errors:** no autonomous story publishing exists yet; it remains
  gated on a shadow trial, provenance checks, correction policy and kill switch.
- **Operations:** alerting, tested backups, deployment rollback and cost
  budgets must be configured before describing the system as production-grade.

Please report suspected vulnerabilities privately to the repository owner.
