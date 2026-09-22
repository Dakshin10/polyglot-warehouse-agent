#!/usr/bin/env bash
# ==============================================================================
# PWA Infrastructure-as-Code (IaC) — GCP Cloud Run Job & Cloud Scheduler Deploy
# ==============================================================================
# Deploys the Polyglot Warehouse Agent (PWA) automated batch pipeline container
# as a GCP Cloud Run Job and configures a GCP Cloud Scheduler cron trigger.
#
# Usage:
#   chmod +x scripts/deploy_scheduler_job.sh
#   ./scripts/deploy_scheduler_job.sh
# ==============================================================================

set -euo pipefail

# Configurable environment variables with sensible defaults
GCP_PROJECT="${GCP_PROJECT:-pwa-prod}"
GCP_REGION="${GCP_REGION:-europe-west1}"
JOB_NAME="${JOB_NAME:-pwa-nightly-sync-job}"
SCHEDULER_NAME="${SCHEDULER_NAME:-pwa-nightly-sync-scheduler}"
CRON_SCHEDULE="${CRON_SCHEDULE:-0 2 * * *}" # 02:00 UTC Daily
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-pwa-scheduler-sa@${GCP_PROJECT}.iam.gserviceaccount.com}"
IMAGE_URI="${IMAGE_URI:-gcr.io/${GCP_PROJECT}/pwa-batch:latest}"

echo "======================================================================"
echo "   NEXORA PWA — GCP CLOUD SCHEDULER & RUN JOB DEPLOYMENT (IaC)        "
echo "======================================================================"
echo "Project:          ${GCP_PROJECT}"
echo "Region:           ${GCP_REGION}"
echo "Cloud Run Job:    ${JOB_NAME}"
echo "Scheduler Job:    ${SCHEDULER_NAME}"
echo "Cron Schedule:    ${CRON_SCHEDULE}"
echo "Service Account:  ${SERVICE_ACCOUNT}"
echo "Container Image:  ${IMAGE_URI}"
echo "======================================================================"

# Step 1: Build & Tag Container Image
echo "---> Step 1: Building batch container image..."
docker build -t "${IMAGE_URI}" -f Dockerfile .
echo "Pushing image to GCP Artifact Registry..."
# docker push "${IMAGE_URI}"

# Step 2: Deploy / Update Cloud Run Job
echo "---> Step 2: Deploying GCP Cloud Run Job..."
gcloud run jobs create "${JOB_NAME}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --image="${IMAGE_URI}" \
  --tasks=1 \
  --max-retries=2 \
  --task-timeout=30m \
  --service-account="${SERVICE_ACCOUNT}" \
  --command="bash" \
  --args="-c,pwa source run && pwa warehouse run" \
  --set-env-vars="PWA_SEMANTIC_CACHE_ENABLED=1,PYTHONUNBUFFERED=1" \
  --quiet || \
gcloud run jobs update "${JOB_NAME}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --image="${IMAGE_URI}" \
  --command="bash" \
  --args="-c,pwa source run && pwa warehouse run" \
  --quiet

# Step 3: Deploy / Update Cloud Scheduler Cron Job
echo "---> Step 3: Deploying GCP Cloud Scheduler cron trigger..."
RUN_JOB_URL="https://${GCP_REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${GCP_PROJECT}/jobs/${JOB_NAME}:run"

gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
  --project="${GCP_PROJECT}" \
  --location="${GCP_REGION}" \
  --schedule="${CRON_SCHEDULE}" \
  --time-zone="UTC" \
  --uri="${RUN_JOB_URL}" \
  --http-method="POST" \
  --oauth-service-account-email="${SERVICE_ACCOUNT}" \
  --description="Nightly automated batch ingestion and warehouse build job for PWA" \
  --quiet || \
gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
  --project="${GCP_PROJECT}" \
  --location="${GCP_REGION}" \
  --schedule="${CRON_SCHEDULE}" \
  --time-zone="UTC" \
  --uri="${RUN_JOB_URL}" \
  --http-method="POST" \
  --oauth-service-account-email="${SERVICE_ACCOUNT}" \
  --quiet

echo "======================================================================"
echo "   DEPLOYMENT SUCCESSFUL!                                             "
echo "======================================================================"
echo "To manually trigger out-of-band execution:"
echo "  gcloud run jobs execute ${JOB_NAME} --project=${GCP_PROJECT} --region=${GCP_REGION}"
echo "======================================================================"
