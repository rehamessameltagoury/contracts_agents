"""Negotiation workflow helpers used by agent tools and FastAPI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from ..config import CONTRACTS_DIR, TRACK_CHANGES_AUTHOR
from ..models import (
    ChangeType,
    ContractChange,
    ContractVersion,
    NegotiationSession,
    utc_now_iso,
)
from ..services import get_artifact_store, get_session_repo
from .docx_revisions import apply_tracked_changes, ensure_docx_from_text
from .email_tool import send_contract_email


def _next_version_label(session: NegotiationSession) -> tuple[str, int]:
    number = session.current_version_number + 1
    return f"v{number}", number


def create_session(
    *,
    contract_name: str,
    client_email: str = "",
    contract_id: Optional[str] = None,
    risk_report_path: Optional[str] = None,
    contract_docx_path: Optional[str] = None,
    contract_text: Optional[str] = None,
    initial_summary: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> NegotiationSession:
    repo = get_session_repo()
    store = get_artifact_store()
    session_id = str(uuid4())
    contract_id = contract_id or session_id

    session = NegotiationSession(
        session_id=session_id,
        contract_id=contract_id,
        contract_name=contract_name,
        client_email=client_email,
        summary=initial_summary
        or f"Session created for '{contract_name}'. Awaiting negotiation redlines.",
        metadata=metadata or {},
    )

    # Baseline contract as v0
    if contract_docx_path:
        src = Path(contract_docx_path)
    elif contract_text:
        src = CONTRACTS_DIR / session_id / "source_v0.docx"
        ensure_docx_from_text(contract_text, src)
    else:
        src = CONTRACTS_DIR / session_id / "source_v0.docx"
        ensure_docx_from_text(f"{contract_name}\n\n[Empty contract placeholder]", src)

    uploaded_contract = store.upload_file(
        src, session_id=session_id, artifact_type="contracts", filename="v0_source.docx"
    )
    report_uri = ""
    report_path = ""
    if risk_report_path and Path(risk_report_path).exists():
        uploaded_report = store.upload_file(
            risk_report_path,
            session_id=session_id,
            artifact_type="reports",
            filename="v0_risk_report.pdf",
        )
        report_uri = uploaded_report["uri"]
        report_path = uploaded_report["path"]

    v0 = ContractVersion(
        contract_version="v0",
        version_number=0,
        risk_report_uri=report_uri,
        risk_report_path=report_path,
        modified_contract_uri=uploaded_contract["uri"],
        modified_contract_path=uploaded_contract["path"],
        source_contract_uri=uploaded_contract["uri"],
        changes=[],
        is_valid=False,
        sent_to_client=False,
        notes="Baseline contract version",
    )
    session.versions.append(v0)
    session.current_version = "v0"
    session.current_version_number = 0
    return repo.save(session)


def append_summary(session: NegotiationSession, turn_note: str) -> str:
    stamp = utc_now_iso()
    addition = f"[{stamp}] {turn_note}".strip()
    if session.summary:
        session.summary = f"{session.summary}\n{addition}"
    else:
        session.summary = addition
    # Keep summary bounded for prompt injection
    lines = session.summary.splitlines()
    if len(lines) > 80:
        session.summary = "\n".join(lines[-80:])
    return session.summary


def apply_negotiation_changes(
    session_id: str,
    changes: list[ContractChange] | list[dict[str, Any]],
    *,
    risk_report_path: Optional[str] = None,
    turn_note: str = "",
    applied_by: str = "negotiation_agent",
) -> dict[str, Any]:
    repo = get_session_repo()
    store = get_artifact_store()
    session = repo.get(session_id)
    if session is None:
        return {"status": "error", "error_message": f"Session not found: {session_id}"}
    if not session.versions:
        return {"status": "error", "error_message": "Session has no baseline contract version"}

    current = session.versions[-1]
    source_path = Path(current.modified_contract_path)
    if not source_path.exists():
        # try re-download from URI
        tmp = CONTRACTS_DIR / session_id / f"{current.contract_version}_source.docx"
        store.download_to_path(current.modified_contract_uri or current.modified_contract_path, tmp)
        source_path = tmp

    version_label, version_number = _next_version_label(session)
    out_path = CONTRACTS_DIR / session_id / f"{version_label}_modified.docx"

    normalized: list[ContractChange] = []
    for item in changes:
        change = item if isinstance(item, ContractChange) else ContractChange.model_validate(item)
        change.applied_by = applied_by
        normalized.append(change)

    applied = apply_tracked_changes(
        source_path,
        out_path,
        normalized,
        author=TRACK_CHANGES_AUTHOR,
    )

    uploaded = store.upload_file(
        out_path,
        session_id=session_id,
        artifact_type="contracts",
        filename=f"{version_label}_modified.docx",
    )

    report_uri = current.risk_report_uri
    report_local = current.risk_report_path
    if risk_report_path and Path(risk_report_path).exists():
        uploaded_report = store.upload_file(
            risk_report_path,
            session_id=session_id,
            artifact_type="reports",
            filename=f"{version_label}_risk_report.pdf",
        )
        report_uri = uploaded_report["uri"]
        report_local = uploaded_report["path"]

    new_version = ContractVersion(
        contract_version=version_label,
        version_number=version_number,
        risk_report_uri=report_uri,
        risk_report_path=report_local,
        modified_contract_uri=uploaded["uri"],
        modified_contract_path=uploaded["path"],
        source_contract_uri=current.modified_contract_uri,
        changes=applied,
        is_valid=False,
        sent_to_client=False,
        notes=turn_note or f"Changes applied by {applied_by}",
    )
    session.versions.append(new_version)
    session.current_version = version_label
    session.current_version_number = version_number
    session.is_valid = False
    session.sent_to_client = False
    append_summary(
        session,
        turn_note
        or f"Applied {len(applied)} tracked change(s) → {version_label}.",
    )
    repo.save(session)

    return {
        "status": "success",
        "session_id": session_id,
        "contract_version": version_label,
        "changes_applied": len(applied),
        "modified_contract_path": uploaded["path"],
        "modified_contract_uri": uploaded["uri"],
        "summary": session.summary,
        "changes": [c.model_dump() for c in applied],
    }


def approve_and_send(
    session_id: str,
    *,
    client_email: Optional[str] = None,
    mark_valid: bool = True,
    send_email: bool = True,
    email_subject: Optional[str] = None,
    email_body: Optional[str] = None,
) -> dict[str, Any]:
    repo = get_session_repo()
    session = repo.get(session_id)
    if session is None:
        return {"status": "error", "error_message": f"Session not found: {session_id}"}
    if not session.versions:
        return {"status": "error", "error_message": "No contract version to approve"}

    current = session.versions[-1]
    to_email = client_email or session.client_email
    email_result: dict[str, Any] = {"status": "skipped", "reason": "send_email=false"}

    if send_email:
        email_result = send_contract_email(
            to_email=to_email,
            subject=email_subject or f"Approved contract: {session.contract_name} ({current.contract_version})",
            body=email_body
            or (
                f"Please find attached the approved contract '{session.contract_name}' "
                f"version {current.contract_version}."
            ),
            attachment_path=current.modified_contract_path,
        )
        if email_result.get("status") != "success":
            return {
                "status": "error",
                "error_message": email_result.get("error_message", "email failed"),
                "email_result": email_result,
            }

    current.is_valid = mark_valid
    current.sent_to_client = bool(send_email and email_result.get("status") == "success")
    session.is_valid = current.is_valid
    session.sent_to_client = current.sent_to_client
    if client_email:
        session.client_email = client_email
    append_summary(
        session,
        f"Legal APPROVED {current.contract_version}. "
        f"is_valid={session.is_valid}, sent_to_client={session.sent_to_client}, to={to_email}.",
    )
    repo.save(session)

    return {
        "status": "success",
        "session_id": session_id,
        "contract_version": current.contract_version,
        "is_valid": session.is_valid,
        "sent_to_client": session.sent_to_client,
        "client_email": to_email,
        "modified_contract_path": current.modified_contract_path,
        "email_result": email_result,
        "summary": session.summary,
    }


def get_session_summary(session_id: str) -> dict[str, Any]:
    session = get_session_repo().get(session_id)
    if session is None:
        return {"status": "error", "error_message": f"Session not found: {session_id}"}
    return {
        "status": "success",
        "session_id": session_id,
        "summary": session.summary,
        "current_version": session.current_version,
        "is_valid": session.is_valid,
        "sent_to_client": session.sent_to_client,
        "contract_name": session.contract_name,
    }


def parse_changes_json(changes_json: str) -> list[ContractChange]:
    data = json.loads(changes_json)
    if not isinstance(data, list):
        raise ValueError("changes_json must be a JSON array")
    return [ContractChange.model_validate(item) for item in data]
