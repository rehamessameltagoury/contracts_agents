"""Pydantic models for negotiation sessions and contract versions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class ContractChange(BaseModel):
    change_id: str = Field(default_factory=lambda: str(uuid4()))
    change_type: ChangeType
    section: str = ""
    old_text: str = ""
    new_text: str = ""
    rationale: str = ""
    applied_by: str = "negotiation_agent"
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=utc_now_iso)


class ContractVersion(BaseModel):
    contract_version: str
    version_number: int
    risk_report_uri: str = ""
    risk_report_path: str = ""
    modified_contract_uri: str = ""
    modified_contract_path: str = ""
    source_contract_uri: str = ""
    changes: list[ContractChange] = Field(default_factory=list)
    is_valid: bool = False
    sent_to_client: bool = False
    created_at: str = Field(default_factory=utc_now_iso)
    notes: str = ""


class NegotiationSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    contract_id: str = ""
    contract_name: str = "Unnamed Contract"
    client_email: str = ""
    summary: str = ""
    is_valid: bool = False
    sent_to_client: bool = False
    current_version: str = "v0"
    current_version_number: int = 0
    time_started: str = Field(default_factory=utc_now_iso)
    last_updated: str = Field(default_factory=utc_now_iso)
    versions: list[ContractVersion] = Field(default_factory=list)
    chat_history: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.last_updated = utc_now_iso()


class CreateSessionRequest(BaseModel):
    contract_name: str = "Unnamed Contract"
    contract_id: Optional[str] = None
    client_email: str = ""
    risk_report_path: Optional[str] = None
    contract_docx_path: Optional[str] = None
    initial_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NegotiateRequest(BaseModel):
    """Initial negotiation: apply guideline-based redlines from risk report."""

    risk_report_text: Optional[str] = None
    changes: Optional[list[ContractChange]] = None
    instructions: str = (
        "Review the risk assessment report and guidelines; apply preferred "
        "fallback language to high/medium risk clauses using Word track changes."
    )


class ChatTurnRequest(BaseModel):
    """Legal counsel chat turn requesting extra contract edits."""

    message: str
    changes: Optional[list[ContractChange]] = None


class ApproveRequest(BaseModel):
    """Approve current version and optionally email the client."""

    client_email: Optional[str] = None
    mark_valid: bool = True
    send_email: bool = True
    email_subject: Optional[str] = None
    email_body: Optional[str] = None


class SessionResponse(BaseModel):
    session: NegotiationSession
    message: str = ""
