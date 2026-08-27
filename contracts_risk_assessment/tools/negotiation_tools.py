"""ADK tools for the Negotiation Agent."""

from __future__ import annotations

import json
from typing import Any, Optional

from ..services.negotiation_workflow import (
    apply_negotiation_changes,
    approve_and_send,
    get_session_summary,
    parse_changes_json,
)
from ..services import get_session_repo
from ..services.negotiation_workflow import append_summary


def apply_contract_tracked_changes(
    session_id: str,
    changes_json: str,
    turn_note: str = "",
    risk_report_path: str = "",
    applied_by: str = "negotiation_agent",
) -> dict[str, Any]:
    """Apply clause edits to the session contract DOCX using Word track changes.

    Args:
        session_id: Negotiation session id.
        changes_json: JSON array of changes. Each item should include
            change_type (added|removed|modified), section, old_text, new_text,
            rationale, and optional metadata.
        turn_note: Short note appended to the Firestore session summary.
        risk_report_path: Optional path to the risk PDF for this version.
        applied_by: Actor label stored on each change row.

    Returns:
        Status payload with new contract_version and change table.
    """
    try:
        changes = parse_changes_json(changes_json)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"Invalid changes_json: {exc}"}

    return apply_negotiation_changes(
        session_id,
        changes,
        risk_report_path=risk_report_path or None,
        turn_note=turn_note,
        applied_by=applied_by,
    )


def update_negotiation_summary(session_id: str, summary_update: str) -> dict[str, Any]:
    """Append/replace context on the session summary stored in Firestore.

    Args:
        session_id: Negotiation session id.
        summary_update: Text to append to the rolling session summary.

    Returns:
        Updated summary payload.
    """
    repo = get_session_repo()
    session = repo.get(session_id)
    if session is None:
        return {"status": "error", "error_message": f"Session not found: {session_id}"}

    append_summary(session, summary_update)
    repo.save(session)
    return {
        "status": "success",
        "session_id": session_id,
        "summary": session.summary,
        "last_updated": session.last_updated,
    }


def load_negotiation_session(session_id: str) -> dict[str, Any]:
    """Load session summary, flags, and latest version metadata from Firestore.

    Args:
        session_id: Negotiation session id.
    """
    return get_session_summary(session_id)


def approve_contract_and_email_client(
    session_id: str,
    client_email: str = "",
    email_subject: str = "",
    email_body: str = "",
) -> dict[str, Any]:
    """Mark the current contract version valid and email the DOCX to the client.

    Called when legal clicks Approve in the frontend.

    Args:
        session_id: Negotiation session id.
        client_email: Override recipient; defaults to session.client_email.
        email_subject: Optional custom subject.
        email_body: Optional custom body.
    """
    return approve_and_send(
        session_id,
        client_email=client_email or None,
        mark_valid=True,
        send_email=True,
        email_subject=email_subject or None,
        email_body=email_body or None,
    )


def get_changes_table(session_id: str, contract_version: str = "") -> dict[str, Any]:
    """Return the changes table for a contract version (default: current).

    Args:
        session_id: Negotiation session id.
        contract_version: Version label like v1; empty uses current.
    """
    session = get_session_repo().get(session_id)
    if session is None:
        return {"status": "error", "error_message": f"Session not found: {session_id}"}
    target = contract_version or session.current_version
    for version in session.versions:
        if version.contract_version == target:
            return {
                "status": "success",
                "session_id": session_id,
                "contract_version": target,
                "changes": [c.model_dump() for c in version.changes],
                "is_valid": version.is_valid,
                "sent_to_client": version.sent_to_client,
                "modified_contract_uri": version.modified_contract_uri,
                "risk_report_uri": version.risk_report_uri,
            }
    return {"status": "error", "error_message": f"Version not found: {target}"}
