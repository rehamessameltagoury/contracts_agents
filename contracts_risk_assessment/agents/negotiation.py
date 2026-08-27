"""Negotiation Agent — redlines DOCX with track changes + approval/email."""

from __future__ import annotations

from google.adk.agents import Agent

from ..config import GEMINI_MODEL, load_guidelines_text, load_prompt
from ..tools.negotiation_tools import (
    apply_contract_tracked_changes,
    approve_contract_and_email_client,
    get_changes_table,
    load_negotiation_session,
    update_negotiation_summary,
)

negotiation_agent = Agent(
    name="negotiation_agent",
    model=GEMINI_MODEL,
    description=(
        "Negotiation / approval agent: reviews Checker risk reports and guidelines, "
        "applies Word track-changes to DOCX contracts, chats with legal for extra "
        "edits, and on Approve emails the modified contract to the client. Persists "
        "versions, change tables, and session summaries to Firestore/GCS."
    ),
    instruction=load_prompt(
        "negotiation",
        risk_guidelines=load_guidelines_text(),
        session_id="{session_id}",
        session_summary="{session_summary}",
    ),
    tools=[
        load_negotiation_session,
        apply_contract_tracked_changes,
        update_negotiation_summary,
        approve_contract_and_email_client,
        get_changes_table,
    ],
)
