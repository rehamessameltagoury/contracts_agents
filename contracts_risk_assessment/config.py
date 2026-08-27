"""Shared configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
GUIDELINES_DIR = PACKAGE_DIR / "guidelines"
GUIDELINES_PDF_PATH = GUIDELINES_DIR / "contract_risk_guidelines.pdf"
REPORTS_DIR = REPO_ROOT / "output" / "reports"
CONTRACTS_DIR = REPO_ROOT / "output" / "contracts"
LOCAL_STORE_DIR = REPO_ROOT / "output" / "local_store"

# Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash")

# GCP
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "contract_sessions")
# When true (default if GCP unset), use local disk + JSON instead of GCS/Firestore
USE_MOCK_GCP = os.getenv(
    "USE_MOCK_GCP",
    "true" if not (GOOGLE_CLOUD_PROJECT and GCS_BUCKET_NAME) else "false",
).lower() in {"1", "true", "yes"}

# Email (approve → send to client)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "noreply@example.com")
EMAIL_SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[Contract Approval]")
# When true, log email instead of sending (useful without SMTP)
EMAIL_DRY_RUN = os.getenv("EMAIL_DRY_RUN", "true").lower() in {"1", "true", "yes"}

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if o.strip()
]

# Negotiation / Word revisions
TRACK_CHANGES_AUTHOR = os.getenv("TRACK_CHANGES_AUTHOR", "Negotiation Agent")


def load_prompt(name: str, **format_kwargs: str) -> str:
    """Load an editable prompt file from prompts/{name}.txt.

    Replaces `{key}` placeholders from kwargs. Unreplaced placeholders (e.g.
    ADK session-state keys like `{liability_assessment}`) are left intact.
    """
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    text = path.read_text(encoding="utf-8")
    for key, value in format_kwargs.items():
        text = text.replace("{" + key + "}", value)
    return text


def load_guidelines_text() -> str:
    """Extract text from the guidelines PDF for prompt injection.

    Agents also accept guidelines as a user/session attachment; this text is
    the editable fallback when no attachment is provided.
    """
    if not GUIDELINES_PDF_PATH.exists():
        return (
            "[GUIDELINES ATTACHMENT PLACEHOLDER]\n"
            "Place contract_risk_guidelines.pdf under "
            f"{GUIDELINES_DIR} or attach the PDF when invoking the agent."
        )
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(GUIDELINES_PDF_PATH))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()
    except Exception as exc:  # noqa: BLE001
        return (
            f"[Failed to read guidelines PDF at {GUIDELINES_PDF_PATH}: {exc}]\n"
            "Attach the guidelines PDF in the conversation, or edit the "
            "prompt files under prompts/."
        )
