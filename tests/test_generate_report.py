"""Smoke test for PDF report generation (no LLM required)."""

from __future__ import annotations

import json
from pathlib import Path

from contracts_risk_assessment.tools.generate_report import generate_risk_report


def test_generate_risk_report_writes_pdf(tmp_path: Path, monkeypatch) -> None:
    import contracts_risk_assessment.tools.generate_report as report_mod

    monkeypatch.setattr(report_mod, "REPORTS_DIR", tmp_path)

    payload = [
        {
            "clause": "Liability",
            "risk": "HIGH",
            "explanation": "Uncapped liability.",
            "findings": ["No LoL clause"],
        },
        {
            "clause": "Termination",
            "risk": "MEDIUM",
            "explanation": "Short auto-renewal notice.",
            "findings": ["15-day notice"],
        },
        {
            "clause": "Intellectual Property",
            "risk": "LOW",
            "explanation": "Provider retains background IP.",
            "findings": [],
        },
        {
            "clause": "Operational & Business",
            "risk": "MEDIUM",
            "explanation": "Net 75 payment terms.",
            "findings": ["Payment > 60 days"],
        },
    ]

    result = generate_risk_report(
        contract_name="Sample MSA",
        overall_risk="HIGH",
        overall_explanation="Liability is uncapped.",
        clause_results_json=json.dumps(payload),
    )

    assert result["status"] == "success"
    report_path = Path(result["report_path"])
    assert report_path.exists()
    assert report_path.stat().st_size > 0
    assert result["overall_risk"] == "HIGH"
