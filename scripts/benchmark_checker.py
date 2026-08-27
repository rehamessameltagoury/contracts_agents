"""Performance benchmark for the Checker multi-agent pipeline.

Measures wall-clock latency, agent/tool event counts, PDF generation, and
whether an overall HIGH/MEDIUM/LOW decision appears in the final response.

Usage (from repo root, with GOOGLE_API_KEY set in .env):

  python scripts/benchmark_checker.py
  python scripts/benchmark_checker.py --runs 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]


async def _run_once(run_index: int, contract_text: str) -> dict:
    from google.adk.runners import InMemoryRunner

    from contracts_risk_assessment.agent import root_agent

    app_name = "contracts_risk_benchmark"
    user_id = "benchmark_user"
    runner = InMemoryRunner(agent=root_agent, app_name=app_name)
    session = await runner.session_service.create_session(
        app_name=app_name,
        user_id=user_id,
    )

    prompt = (
        "Please perform a full contract risk assessment against our risk "
        "guidelines and generate the PDF risk report.\n\n"
        f"CONTRACT:\n{contract_text}"
    )
    user_message = types.Content(role="user", parts=[types.Part(text=prompt)])

    started = time.perf_counter()
    events = 0
    agent_names: list[str] = []
    tool_calls: list[str] = []
    final_text_parts: list[str] = []
    report_paths: list[str] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=user_message,
    ):
        events += 1
        author = getattr(event, "author", None)
        if author:
            agent_names.append(str(author))

        content = getattr(event, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                text = getattr(part, "text", None)
                if text:
                    final_text_parts.append(text)
                fn = getattr(part, "function_call", None)
                if fn and getattr(fn, "name", None):
                    tool_calls.append(fn.name)
                fr = getattr(part, "function_response", None)
                if fr and getattr(fr, "response", None):
                    response = fr.response
                    if isinstance(response, dict) and response.get("report_path"):
                        report_paths.append(str(response["report_path"]))

    elapsed = time.perf_counter() - started
    final_text = "\n".join(final_text_parts)
    upper = final_text.upper()
    overall = None
    for level in ("HIGH", "MEDIUM", "LOW"):
        if f"OVERALL" in upper and level in upper:
            # Prefer explicit overall mentions; fall back below.
            overall = level
            break
    if overall is None:
        for level in ("HIGH", "MEDIUM", "LOW"):
            if level in upper:
                overall = level
                break

    unique_agents = list(dict.fromkeys(agent_names))
    report_path = report_paths[-1] if report_paths else None
    report_ok = bool(report_path and Path(report_path).exists())

    return {
        "run": run_index,
        "elapsed_seconds": round(elapsed, 2),
        "events": events,
        "agents_seen": unique_agents,
        "tool_calls": tool_calls,
        "overall_risk_detected": overall,
        "report_path": report_path,
        "report_exists": report_ok,
        "final_response_chars": len(final_text),
        "final_response_preview": final_text[-800:],
    }


async def main_async(runs: int) -> int:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key or api_key.startswith("your_"):
        print(
            "GOOGLE_API_KEY is not set.\n"
            "1) Copy .env.example to .env\n"
            "2) Set GOOGLE_API_KEY=...\n"
            "3) Re-run: python scripts/benchmark_checker.py"
        )
        return 2

    contract_path = ROOT / "tests" / "fixtures" / "sample_high_risk_contract.txt"
    contract_text = contract_path.read_text(encoding="utf-8")

    print(f"Model: {os.getenv('GEMINI_MODEL', 'gemini-3-flash')}")
    print(f"Runs: {runs}")
    print(f"Contract fixture: {contract_path.name}")
    print("-" * 60)

    results = []
    for i in range(1, runs + 1):
        print(f"Starting run {i}/{runs}...")
        result = await _run_once(i, contract_text)
        results.append(result)
        print(
            f"  elapsed={result['elapsed_seconds']}s | "
            f"overall={result['overall_risk_detected']} | "
            f"pdf={result['report_exists']} | "
            f"tools={result['tool_calls']} | "
            f"agents={len(result['agents_seen'])}"
        )

    elapsed_values = [r["elapsed_seconds"] for r in results]
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": os.getenv("GEMINI_MODEL", "gemini-3-flash"),
        "runs": runs,
        "latency_seconds": {
            "min": min(elapsed_values),
            "max": max(elapsed_values),
            "mean": round(statistics.mean(elapsed_values), 2),
            "stdev": round(statistics.stdev(elapsed_values), 2) if runs > 1 else 0.0,
        },
        "pdf_success_rate": round(
            sum(1 for r in results if r["report_exists"]) / runs, 2
        ),
        "overall_high_rate": round(
            sum(1 for r in results if r["overall_risk_detected"] == "HIGH") / runs, 2
        ),
        "results": results,
    }

    out_dir = ROOT / "output" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"checker_benchmark_{stamp}.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("-" * 60)
    print("SUMMARY")
    print(f"  latency mean: {summary['latency_seconds']['mean']}s")
    print(f"  latency min/max: {summary['latency_seconds']['min']}s / {summary['latency_seconds']['max']}s")
    print(f"  PDF success rate: {summary['pdf_success_rate']}")
    print(f"  Overall HIGH rate (expected for fixture): {summary['overall_high_rate']}")
    print(f"  Saved: {out_path}")

    # Soft pass criteria for this intentionally high-risk fixture.
    if summary["pdf_success_rate"] < 1.0 or summary["overall_high_rate"] < 1.0:
        print("WARNING: quality gates not fully met for the high-risk sample.")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Checker agent performance")
    parser.add_argument("--runs", type=int, default=1, help="Number of timed runs")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args.runs)))


if __name__ == "__main__":
    main()
