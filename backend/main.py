"""FastAPI backend for Checker + Negotiation frontend workflows."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contracts_risk_assessment.config import CORS_ORIGINS
from backend.routers import health, sessions

app = FastAPI(
    title="Contracts Risk & Negotiation API",
    description=(
        "Backend for Checker risk reports and Negotiation Agent workflows: "
        "DOCX track-changes, legal chat, approve + email, Firestore/GCS persistence."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sessions.router, prefix="/api")


@app.on_event("startup")
def _ensure_dirs() -> None:
    from contracts_risk_assessment.config import CONTRACTS_DIR, LOCAL_STORE_DIR, REPORTS_DIR

    for path in (REPORTS_DIR, CONTRACTS_DIR, LOCAL_STORE_DIR):
        Path(path).mkdir(parents=True, exist_ok=True)
