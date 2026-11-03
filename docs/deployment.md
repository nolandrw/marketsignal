# Deploying a scheduled collector (not yet provisioned)

This is a **runbook and an opt-in deployment script**, not evidence of a live
service. No cloud accounts, database, secrets, paid resources, schedule, or
publishing permissions are created by the repository alone.

## Architecture and minimum viable cost footprint

- Supabase PostgreSQL holds durable markets, snapshots, signals, run audits and
  metadata. Use a separate project for MarketSignal.
- Cloud Build produces one container, stored in Artifact Registry.
- Cloud Run **Jobs** run one short-lived Python task per invocation. No
  continuously running web server or worker is needed.
- Cloud Scheduler can invoke the job every 15 minutes using an OAuth service
  account; it is deliberately **not enabled** by the deployment script.
- Secret Manager supplies the restricted PostgreSQL URL. No secret value is
  embedded in an image, script, YAML file, or git commit.
- No AI agent, public website deployment, or email delivery exists yet.

Cloud and database providers can charge even when traffic is low. Set a
Google Cloud billing budget and alert, and review Supabase limits, *before*
running anything in this document. A budget alert is not a hard spending cap.

## 1. Create the database and initialize schema

Create a dedicated Supabase project. In its Connect dialog, copy a PostgreSQL
URI with SSL enabled (add `sslmode=require`). For a Cloud Run workload needing
IPv4, the shared **session pooler** (port 5432) is the straightforward option;
copy its host rather than guessing it. Direct database URLs may require IPv6.

From a trusted machine with Python 3.11+ and the repository:

```bash
python -m pip install '.[postgres]'
# Enter the privileged URI without leaving the password in shell history.
read -r -s -p 'Privileged PostgreSQL URI: ' DATABASE_URL
export DATABASE_URL
python -m marketsignal init-db
unset DATABASE_URL
```

For migrations, the privileged URI must have table-creation rights. It should
**never** be used as the scheduled worker credential.

With a privileged SQL editor, create a dedicated login. Replace the placeholder
with a randomly generated password **in the private SQL editor**, not in a
tracked file:

```sql
CREATE ROLE marketsignal_worker LOGIN PASSWORD '<GENERATE_PRIVATE_PASSWORD>';
GRANT USAGE ON SCHEMA public TO marketsignal_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  public.markets, public.snapshots, public.signals, public.runs, public.metadata
  TO marketsignal_worker;
GRANT USAGE, SELECT ON SEQUENCE
  public.signals_signal_id_seq, public.runs_run_id_seq
  TO marketsignal_worker;

CREATE POLICY worker_rw ON public.markets FOR ALL TO marketsignal_worker
  USING (true) WITH CHECK (true);
CREATE POLICY worker_rw ON public.snapshots FOR ALL TO marketsignal_worker
  USING (true) WITH CHECK (true);
CREATE POLICY worker_rw ON public.signals FOR ALL TO marketsignal_worker
  USING (true) WITH CHECK (true);
CREATE POLICY worker_rw ON public.runs FOR ALL TO marketsignal_worker
  USING (true) WITH CHECK (true);
CREATE POLICY worker_rw ON public.metadata FOR ALL TO marketsignal_worker
  USING (true) WITH CHECK (true);
```

Row-level security is enabled during `init-db`; these policies allow only the
named worker role to read/write project tables. The worker has no DDL grants
and is not the table owner. Anonymous browser users are not granted access.

For the shared Supabase pooler, a custom role's user portion is
`marketsignal_worker.<PROJECT_REF>` (not just `marketsignal_worker`). Use the
host and port copied from Supabase, the restricted password, and `sslmode=require`
to construct the worker URI. Test locally with:

```bash
read -r -s -p 'Restricted worker URI: ' DATABASE_URL
export DATABASE_URL REQUIRE_PERSISTENT_DB=1
python -m marketsignal collect --max-markets 50 --max-pages 3
python -m marketsignal health
unset DATABASE_URL REQUIRE_PERSISTENT_DB
```

Note: the health check returns failure until an `ok` run exists; its default
freshness window is 35 minutes. The collector must later be executed repeatedly
to establish a 1h/24h baseline before meaningful movement signals are possible.

## 2. Store the restricted credential in Secret Manager

Create a Google Cloud project with billing and install/authenticate the `gcloud`
CLI. In **Secret Manager**, create a secret such as `marketsignal-db-url` and
add the *restricted worker* URI as version 1. Do not use the privileged URI.
Do not paste it into a shell command, repository secret, or issue.

The deployment script checks that the secret version exists; it does not
read, generate, or print the credential. It grants Secret Accessor on that one
secret to `marketsignal-worker` rather than broad project access.

## 3. Deploy a single job — scheduling stays OFF

```bash
export GCP_PROJECT_ID='YOUR_PROJECT_ID'
export GCP_REGION='us-west1'
export DB_SECRET_NAME='marketsignal-db-url'
export DB_SECRET_VERSION='1'
export MARKETSIGNAL_DEPLOY_APPROVED=yes
bash scripts/deploy_gcp.sh
unset MARKETSIGNAL_DEPLOY_APPROVED
```

The script enables required Google APIs, creates the image repository and
two narrowly scoped service accounts, builds the image, deploys one Cloud Run
Job, and grants its invocation permission to the scheduler account. The job
uses a single task, limited retries, and a four-minute task timeout.

Before enabling any schedule, inspect and run the job once:

```bash
gcloud run jobs execute marketsignal-collector \
  --region="$GCP_REGION" --project="$GCP_PROJECT_ID" --wait
gcloud run jobs executions list \
  --job=marketsignal-collector --region="$GCP_REGION" \
  --project="$GCP_PROJECT_ID"
```

Verify an `ok` run in PostgreSQL and look for credentials or query URLs in
Cloud Logging. If a job fails, check its identity, Secret Manager access,
database host/port, worker role policies, and connection pooler username.

## 4. Activate the unattended schedule (separate decision)

Only after validating data ingestion and expected costs:

```bash
export MARKETSIGNAL_SCHEDULE_APPROVED=yes
bash scripts/enable_schedule_gcp.sh
unset MARKETSIGNAL_SCHEDULE_APPROVED
```

This creates or updates a schedule to launch the job every 15 minutes. It uses
an OAuth token representing `marketsignal-scheduler`; the target is Google's
`run.googleapis.com` endpoint, not a public MarketSignal URL.

To stop future launches without deleting evidence or configuration:

```bash
gcloud scheduler jobs pause marketsignal-quarter-hour \
  --location="$GCP_REGION" --project="$GCP_PROJECT_ID"
```

## 5. Operational checks and limitations

- Check `python -m marketsignal health` against hosted PostgreSQL; **no remote
  monitoring or paging is configured yet**. This is the next operations task.
- Record actual collection coverage over at least seven days before claiming
  unattended reliability. A successful single job is not a quality metric.
- Snapshot retention defaults to 30 days, except quotes referenced by signals.
  This limits accumulation but may constrain later model calibration.
- Create a tested backup/restore plan and add migration versioning before
  schema evolution. Supabase backups depend on the chosen plan.
- Rotate the worker password in the database and add a *new Secret Manager
  version*. Redeploy with `DB_SECRET_VERSION` set to the new version; do not
  alter the secret in source code.
- No article generation, autonomous publication, reader authentication,
  newsletter sends or static-site export is enabled. Publication must pass a
  separate source-verification and safety evaluation milestone.

Official references:

- [Cloud Run Jobs and Cloud Scheduler](https://cloud.google.com/run/docs/execute/jobs-on-schedule)
- [Cloud Run Jobs secrets](https://cloud.google.com/run/docs/configuring/jobs/secrets)
- [Supabase PostgreSQL connection methods](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security)
