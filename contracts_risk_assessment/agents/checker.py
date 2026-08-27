"""Checker agent: parallel clause review + synthesis + PDF report."""

from __future__ import annotations

from google.adk.agents import Agent, ParallelAgent, SequentialAgent

from .clause_agents import CLAUSE_AGENTS
from ..config import GEMINI_MODEL, load_guidelines_text, load_prompt
from ..tools import generate_risk_report

clause_review_team = ParallelAgent(
    name="clause_review_team",
    description=(
        "Runs Liability, Termination, Intellectual Property, and Operational & "
        "Business clause assessors in parallel."
    ),
    sub_agents=list(CLAUSE_AGENTS),
)

checker_synthesizer = Agent(
    name="checker_synthesizer",
    model=GEMINI_MODEL,
    description=(
        "Combines clause assessments, decides overall HIGH/MEDIUM/LOW risk, "
        "and generates the PDF risk report."
    ),
    instruction=load_prompt(
        "checker",
        risk_guidelines=load_guidelines_text(),
        session_summary="{session_summary}",
    ),
    tools=[generate_risk_report],
)

# Root specialist used by the Orchestrator (more agents can be added later beside this).
checker_agent = SequentialAgent(
    name="checker_agent",
    description=(
        "Checker Agent: reviews a contract against risk guidelines for Liability, "
        "Termination, Intellectual Property, and Operational & Business clauses, "
        "then produces a PDF risk report with an overall HIGH/MEDIUM/LOW decision."
    ),
    sub_agents=[clause_review_team, checker_synthesizer],
)
