#!/usr/bin/env bash
# Keep unattended execution opt-in until a shadow run passes acceptance checks.
set -euo pipefail

if [[ "${MARKETSIGNAL_SCHEDULE_APPROVED:-}" != "yes" ]]; then
  echo 'Scheduling requires MARKETSIGNAL_SCHEDULE_APPROVED=yes.' >&2
  exit 2
fi
: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
GCP_REGION="${GCP_REGION:-us-west1}"
JOB_NAME="${JOB_NAME:-marketsignal-collector}"
SCHEDULE_NAME="${SCHEDULE_NAME:-marketsignal-quarter-hour}"
SCHEDULER_EMAIL="marketsignal-scheduler@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
URI="https://run.googleapis.com/v2/projects/${GCP_PROJECT_ID}/locations/${GCP_REGION}/jobs/${JOB_NAME}:run"

command -v gcloud >/dev/null || { echo 'Install the Google Cloud CLI.' >&2; exit 2; }
gcloud run jobs describe "${JOB_NAME}" \
  --region="${GCP_REGION}" --project="${GCP_PROJECT_ID}" >/dev/null

if gcloud scheduler jobs describe "${SCHEDULE_NAME}" \
    --location="${GCP_REGION}" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULE_NAME}" \
    --location="${GCP_REGION}" --project="${GCP_PROJECT_ID}" \
    --schedule='*/15 * * * *' --time-zone='Etc/UTC' \
    --uri="${URI}" --http-method=POST \
    --oauth-service-account-email="${SCHEDULER_EMAIL}" \
    --max-retry-attempts=2 --max-backoff=600s
  state="$(gcloud scheduler jobs describe "${SCHEDULE_NAME}" \
    --location="${GCP_REGION}" --project="${GCP_PROJECT_ID}" \
    --format='value(state)')"
  if [[ "${state}" == 'PAUSED' ]]; then
    gcloud scheduler jobs resume "${SCHEDULE_NAME}" \
      --location="${GCP_REGION}" --project="${GCP_PROJECT_ID}"
  fi
else
  gcloud scheduler jobs create http "${SCHEDULE_NAME}" \
    --location="${GCP_REGION}" --project="${GCP_PROJECT_ID}" \
    --schedule='*/15 * * * *' --time-zone='Etc/UTC' \
    --uri="${URI}" --http-method=POST \
    --oauth-service-account-email="${SCHEDULER_EMAIL}" \
    --max-retry-attempts=2 --max-backoff=600s
fi
echo "Enabled the 15-minute schedule '${SCHEDULE_NAME}'."
