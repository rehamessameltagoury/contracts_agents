"""Session / negotiation / approval API for the frontend."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.agent_runner import run_negotiation_turn
from contracts_risk_assessment.config import CONTRACTS_DIR
from contracts_risk_assessment.models import (
    ApproveRequest,
    ChatTurnRequest,
    CreateSessionRequest,
    NegotiateRequest,
    SessionResponse,
)
from contracts_risk_assessment.services import get_session_repo
from contracts_risk_assessment.services.negotiation_workflow import (
    append_summary,
    apply_negotiation_changes,
    approve_and_send,
    create_session,
)
from contracts_risk_assessment.tools.docx_revisions import ensure_docx_from_text

router = APIRouter(tags=["sessions"])


def _session_or_404(session_id: str):
    session = get_session_repo().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session


@router.post("/sessions", response_model=SessionResponse)
async def create_negotiation_session(
    contract_name: str = Form("Unnamed Contract"),
    client_email: str = Form(""),
    contract_id: Optional[str] = Form(None),
    initial_summary: str = Form(""),
    contract_docx: Optional[UploadFile] = File(None),
    risk_report_pdf: Optional[UploadFile] = File(None),
    contract_text: Optional[str] = Form(None),
):
    """Create a negotiation session from Checker output + contract DOCX/text.

    Frontend typically calls this after the Checker finishes a risk report.
    """
    tmp_dir = CONTRACTS_DIR / "_uploads" / str(uuid4())
    tmp_dir.mkdir(parents=True, exist_ok=True)
    docx_path = None
    report_path = None

    try:
        if contract_docx is not None:
            docx_path = tmp_dir / (contract_docx.filename or "contract.docx")
            with docx_path.open("wb") as f:
                shutil.copyfileobj(contract_docx.file, f)
        if risk_report_pdf is not None:
            report_path = tmp_dir / (risk_report_pdf.filename or "risk_report.pdf")
            with report_path.open("wb") as f:
                shutil.copyfileobj(risk_report_pdf.file, f)

        session = create_session(
            contract_name=contract_name,
            client_email=client_email,
            contract_id=contract_id,
            risk_report_path=str(report_path) if report_path else None,
            contract_docx_path=str(docx_path) if docx_path else None,
            contract_text=contract_text,
            initial_summary=initial_summary,
        )
        return SessionResponse(session=session, message="Session created")
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/sessions/json", response_model=SessionResponse)
def create_session_json(body: CreateSessionRequest):
    """JSON alternative for creating a session when files are already on disk."""
    session = create_session(
        contract_name=body.contract_name,
        client_email=body.client_email,
        contract_id=body.contract_id,
        risk_report_path=body.risk_report_path,
        contract_docx_path=body.contract_docx_path,
        initial_summary=body.initial_summary,
        metadata=body.metadata,
    )
    return SessionResponse(session=session, message="Session created")


@router.get("/sessions")
def list_sessions(limit: int = 50):
    return {"sessions": [s.model_dump() for s in get_session_repo().list_sessions(limit=limit)]}


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    session = _session_or_404(session_id)
    return SessionResponse(session=session)


@router.get("/sessions/{session_id}/summary")
def get_summary(session_id: str):
    """Rolling session summary for Checker/Orchestrator history injection."""
    session = _session_or_404(session_id)
    return {
        "session_id": session_id,
        "summary": session.summary,
        "current_version": session.current_version,
        "is_valid": session.is_valid,
        "sent_to_client": session.sent_to_client,
        "time_started": session.time_started,
        "last_updated": session.last_updated,
    }


@router.post("/sessions/{session_id}/negotiate", response_model=SessionResponse)
async def negotiate(session_id: str, body: NegotiateRequest):
    """Option bootstrap: apply risk-based redlines (deterministic changes and/or LLM).

    Prefer providing `changes` from the frontend/LLM. If omitted, the Negotiation
    Agent is invoked to propose and apply edits from the risk report text.
    """
    session = _session_or_404(session_id)

    if body.changes:
        result = apply_negotiation_changes(
            session_id,
            body.changes,
            turn_note=body.instructions[:300],
            applied_by="negotiation_agent",
        )
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail=result)
        session = _session_or_404(session_id)
        return SessionResponse(
            session=session,
            message=f"Applied {result.get('changes_applied')} tracked changes → {result.get('contract_version')}",
        )

    # LLM path
    message = (
        f"{body.instructions}\n\n"
        "Use apply_contract_tracked_changes with concrete edits. "
        f"Risk report text:\n{body.risk_report_text or '(see session risk report)'}"
    )
    agent_result = await run_negotiation_turn(
        message=message,
        session_id=session_id,
        session_summary=session.summary,
    )
    session = _session_or_404(session_id)
    session.chat_history.append(
        {"role": "system", "event": "negotiate", "agent": agent_result}
    )
    get_session_repo().save(session)
    return SessionResponse(
        session=session,
        message=agent_result.get("response_text") or "Negotiation turn completed",
    )


@router.post("/sessions/{session_id}/chat", response_model=SessionResponse)
async def chat_turn(session_id: str, body: ChatTurnRequest):
    """Option 2: legal chat window — request extra tracked changes, then later Approve."""
    session = _session_or_404(session_id)
    session.chat_history.append({"role": "legal", "message": body.message})

    if body.changes:
        result = apply_negotiation_changes(
            session_id,
            body.changes,
            turn_note=f"Legal chat edit: {body.message[:200]}",
            applied_by="legal_chat",
        )
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail=result)
        session = _session_or_404(session_id)
        session.chat_history.append(
            {
                "role": "agent",
                "message": f"Applied {result.get('changes_applied')} changes → {result.get('contract_version')}",
            }
        )
        get_session_repo().save(session)
        return SessionResponse(session=session, message=session.chat_history[-1]["message"])

    agent_result = await run_negotiation_turn(
        message=(
            "LEGAL CHAT EDIT REQUEST. Apply extra tracked changes as asked, "
            "update the session summary, and do NOT email the client yet.\n\n"
            f"{body.message}"
        ),
        session_id=session_id,
        session_summary=session.summary,
    )
    session = _session_or_404(session_id)
    session.chat_history.append(
        {"role": "agent", "message": agent_result.get("response_text", ""), "meta": agent_result}
    )
    append_summary(session, f"Chat turn: {body.message[:180]}")
    get_session_repo().save(session)
    return SessionResponse(
        session=session,
        message=agent_result.get("response_text") or "Chat turn completed",
    )


@router.post("/sessions/{session_id}/approve")
def approve(session_id: str, body: ApproveRequest):
    """Option 1: legal clicks Approve → mark valid + email modified DOCX to client."""
    _session_or_404(session_id)
    result = approve_and_send(
        session_id,
        client_email=body.client_email,
        mark_valid=body.mark_valid,
        send_email=body.send_email,
        email_subject=body.email_subject,
        email_body=body.email_body,
    )
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result)
    session = _session_or_404(session_id)
    return {"result": result, "session": session.model_dump()}


@router.get("/sessions/{session_id}/versions")
def list_versions(session_id: str):
    session = _session_or_404(session_id)
    return {
        "session_id": session_id,
        "current_version": session.current_version,
        "versions": [v.model_dump() for v in session.versions],
    }


@router.get("/sessions/{session_id}/versions/{version}")
def get_version(session_id: str, version: str):
    session = _session_or_404(session_id)
    for item in session.versions:
        if item.contract_version == version:
            return item.model_dump()
    raise HTTPException(status_code=404, detail=f"Version not found: {version}")


@router.get("/sessions/{session_id}/changes")
def get_changes(session_id: str, version: Optional[str] = None):
    """Changes table (removed/added/modified + metadata) for a contract version."""
    session = _session_or_404(session_id)
    target = version or session.current_version
    for item in session.versions:
        if item.contract_version == target:
            return {
                "session_id": session_id,
                "contract_version": target,
                "changes": [c.model_dump() for c in item.changes],
            }
    raise HTTPException(status_code=404, detail=f"Version not found: {target}")


@router.get("/sessions/{session_id}/download/contract")
def download_contract(session_id: str, version: Optional[str] = None):
    session = _session_or_404(session_id)
    target = version or session.current_version
    for item in session.versions:
        if item.contract_version == target:
            path = Path(item.modified_contract_path)
            if not path.exists():
                raise HTTPException(status_code=404, detail="Contract file missing on disk")
            return FileResponse(
                path,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=path.name,
            )
    raise HTTPException(status_code=404, detail=f"Version not found: {target}")


@router.get("/sessions/{session_id}/download/report")
def download_report(session_id: str, version: Optional[str] = None):
    session = _session_or_404(session_id)
    target = version or session.current_version
    for item in session.versions:
        if item.contract_version == target:
            path = Path(item.risk_report_path) if item.risk_report_path else None
            if path is None or not path.exists():
                raise HTTPException(status_code=404, detail="Risk report not available for this version")
            return FileResponse(path, media_type="application/pdf", filename=path.name)
    raise HTTPException(status_code=404, detail=f"Version not found: {target}")


@router.post("/sessions/{session_id}/text-to-docx")
def text_to_docx(session_id: str, text: str = Form(...)):
    """Utility: materialize plain text into a DOCX baseline for the session."""
    session = _session_or_404(session_id)
    out = CONTRACTS_DIR / session_id / "imported_text.docx"
    ensure_docx_from_text(text, out)
    return {"status": "success", "path": str(out), "session_id": session_id}
