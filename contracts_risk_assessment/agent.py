"""Root Orchestrator agent for contract risk assessment + negotiation.

Run with:
  adk web .
  adk run contracts_risk_assessment

API (frontend):
  uvicorn backend.main:app --reload --port 8080
"""

from __future__ import annotations

from google.adk.agents import Agent

from .agents.checker import checker_agent
from .agents.negotiation import negotiation_agent
from .config import GEMINI_MODEL, load_prompt

root_agent = Agent(
    name="orchestrator",
    model=GEMINI_MODEL,
    description=(
        "Root orchestrator for company contract risk assessment and negotiation. "
        "Delegates to Checker for risk reports and Negotiation for DOCX redlines, "
        "legal chat, approval, and client email."
    ),
    instruction=load_prompt(
        "orchestrator",
        session_summary="{session_summary}",
    ),
    sub_agents=[
        checker_agent,
        negotiation_agent,
    ],
)
