"""Clause specialist agents used by the Checker."""

from __future__ import annotations

from google.adk.agents import Agent

from ..config import GEMINI_MODEL, load_guidelines_text, load_prompt

_GUIDELINES = load_guidelines_text()


def _clause_agent(name: str, prompt_file: str, description: str, output_key: str) -> Agent:
    return Agent(
        name=name,
        model=GEMINI_MODEL,
        description=description,
        instruction=load_prompt(prompt_file, risk_guidelines=_GUIDELINES),
        output_key=output_key,
    )


liability_clause_agent = _clause_agent(
    name="liability_clause_agent",
    prompt_file="liability_clause",
    description=(
        "Assesses Liability & Indemnification clauses (caps, indemnities, "
        "consequential damages) against risk guidelines."
    ),
    output_key="liability_assessment",
)

termination_clause_agent = _clause_agent(
    name="termination_clause_agent",
    prompt_file="termination_clause",
    description=(
        "Assesses Termination rights (cause/convenience, cure periods, "
        "auto-renewal notice) against risk guidelines."
    ),
    output_key="termination_assessment",
)

intellectual_property_clause_agent = _clause_agent(
    name="intellectual_property_clause_agent",
    prompt_file="intellectual_property_clause",
    description=(
        "Assesses Intellectual Property clauses (background IP, work-for-hire, "
        "licenses) against risk guidelines."
    ),
    output_key="ip_assessment",
)

operational_business_clause_agent = _clause_agent(
    name="operational_business_clause_agent",
    prompt_file="operational_business_clause",
    description=(
        "Assesses Operational & Business terms (payment, scope, SLA, related "
        "privacy/ops risks) against risk guidelines."
    ),
    output_key="operational_assessment",
)

CLAUSE_AGENTS = [
    liability_clause_agent,
    termination_clause_agent,
    intellectual_property_clause_agent,
    operational_business_clause_agent,
]
