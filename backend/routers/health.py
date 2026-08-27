"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from contracts_risk_assessment.config import (
    EMAIL_DRY_RUN,
    FIRESTORE_COLLECTION,
    GCS_BUCKET_NAME,
    GEMINI_MODEL,
    GOOGLE_CLOUD_PROJECT,
    USE_MOCK_GCP,
)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": GEMINI_MODEL,
        "use_mock_gcp": USE_MOCK_GCP,
        "google_cloud_project": GOOGLE_CLOUD_PROJECT or None,
        "gcs_bucket": GCS_BUCKET_NAME or None,
        "firestore_collection": FIRESTORE_COLLECTION,
        "email_dry_run": EMAIL_DRY_RUN,
    }
