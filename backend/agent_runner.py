"""Helpers to invoke ADK agents from FastAPI."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from google.genai import types


async def run_negotiation_turn(
    *,
    message: str,
    session_id: str,
    session_summary: str = "",
) -> dict[str, Any]:
    """Run one turn against the negotiation agent (via root orchestrator routing)."""
    from google.adk.runners import InMemoryRunner

    from contracts_risk_assessment.agents.negotiation import negotiation_agent

    app_name = "contracts_negotiation_api"
    user_id = f"legal_{session_id}"
    runner = InMemoryRunner(agent=negotiation_agent, app_name=app_name)
    session = await runner.session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        state={
            "session_id": session_id,
            "session_summary": session_summary,
        },
    )

    prompt = (
        f"session_id={session_id}\n"
        f"session_summary:\n{session_summary}\n\n"
        f"{message}"
    )
    user_message = types.Content(role="user", parts=[types.Part(text=prompt)])

    texts: list[str] = []
    tool_calls: list[str] = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=user_message,
    ):
        content = getattr(event, "content", None)
        if not content or not getattr(content, "parts", None):
            continue
        for part in content.parts:
            if getattr(part, "text", None):
                texts.append(part.text)
            fn = getattr(part, "function_call", None)
            if fn and getattr(fn, "name", None):
                tool_calls.append(fn.name)

    return {
        "status": "success",
        "response_text": "\n".join(texts).strip(),
        "tool_calls": tool_calls,
    }


def run_negotiation_turn_sync(
    *,
    message: str,
    session_id: str,
    session_summary: str = "",
) -> dict[str, Any]:
    return asyncio.run(
        run_negotiation_turn(
            message=message,
            session_id=session_id,
            session_summary=session_summary,
        )
    )
