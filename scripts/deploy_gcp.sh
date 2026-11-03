#!/usr/bin/env bash
# Explicitly approved, one-time Cloud Run deployment. No secret values accepted.
set -euo pipefail

if [[ "${MARKETSIGNAL_DEPLOY_APPROVED:-}" != "yes" ]]; then
  echo 'Deployment requires MARKETSIGNAL_DEPLOY_APPROVED=yes (cloud charges may apply).' >&2
  exit 2
fi

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
: "${DB_SECRET_NAME:?Set DB_SECRET_NAME to an existing Secret Manager secret}"
GCP_REGION="${GCP_REGION:-us-west1}"
JOB_NAME="${JOB_NAME:-marketsignal-collector}"
ARTIFACT_REPO="${ARTIFACT_REPO:-marketsignal}"
DB_SECRET_VERSION="${DB_SECRET_VERSION:-1}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d%H%M%S)}"
WORKER_EMAIL="marketsignal-worker@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_EMAIL="marketsignal-scheduler@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
IMAGE_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REPO}/collector:${IMAGE_TAG}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v gcloud >/dev/null || { echo 'Install the Google Cloud CLI.' >&2; exit 2; }
gcloud auth list --filter='status:ACTIVE' --format='value(account)' | head -n 1 | grep -q . || {
  echo 'Authenticate using gcloud auth login before running.' >&2
  exit 2
}

# These permissions apply only to this project and its explicit resources.
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com iam.googleapis.com \
  --project="${GCP_PROJECT_ID}"

gcloud secrets versions describe "${DB_SECRET_VERSION}" \
  --secret="${DB_SECRET_NAME}" --project="${GCP_PROJECT_ID}" >/dev/null || {
    echo 'Database secret or version does not exist. Add it in Secret Manager first.' >&2
    exit 2
  }

if ! gcloud artifacts repositories describe "${ARTIFACT_REPO}" \
  --location="${GCP_REGION}" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${ARTIFACT_REPO}" \
    --repository-format=docker --location="${GCP_REGION}" \
    --description='MarketSignal collector images' --project="${GCP_PROJECT_ID}"
fi

for account in marketsignal-worker marketsignal-scheduler; do
  if ! gcloud iam service-accounts describe \
    "${account}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
    --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${account}" \
      --display-name="MarketSignal ${account}" --project="${GCP_PROJECT_ID}"
  fi
done

gcloud secrets add-iam-policy-binding "${DB_SECRET_NAME}" \
  --member="serviceAccount:${WORKER_EMAIL}" \
  --role='roles/secretmanager.secretAccessor' --project="${GCP_PROJECT_ID}"

gcloud builds submit "${PROJECT_ROOT}" --tag="${IMAGE_URI}" --project="${GCP_PROJECT_ID}"
gcloud run jobs deploy "${JOB_NAME}" \
  --image="${IMAGE_URI}" --region="${GCP_REGION}" --project="${GCP_PROJECT_ID}" \
  --service-account="${WORKER_EMAIL}" \
  --set-secrets="DATABASE_URL=${DB_SECRET_NAME}:${DB_SECRET_VERSION}" \
  --set-env-vars='REQUIRE_PERSISTENT_DB=1' \
  --tasks=1 --parallelism=1 --max-retries=2 --task-timeout=240s \
  --cpu=1 --memory=512Mi

gcloud run jobs add-iam-policy-binding "${JOB_NAME}" \
  --member="serviceAccount:${SCHEDULER_EMAIL}" \
  --role='roles/run.invoker' --region="${GCP_REGION}" \
  --project="${GCP_PROJECT_ID}"

echo "Deployed ${JOB_NAME} using image ${IMAGE_URI}."
echo 'No schedule was enabled; manually execute and verify before scheduling.'
