"""PDF risk-report generation tool for the Checker agent."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import REPORTS_DIR

try:
    from google.adk.tools import ToolContext
except ImportError:  # pragma: no cover
    ToolContext = Any  # type: ignore[misc, assignment]


_RISK_COLORS = {
    "HIGH": colors.HexColor("#B42318"),
    "MEDIUM": colors.HexColor("#B54708"),
    "LOW": colors.HexColor("#027A48"),
}


def _normalize_risk(value: str) -> str:
    raw = (value or "").strip().upper()
    if raw in {"CRITICAL", "CRIT"}:
        return "HIGH"
    if raw in {"HIGH", "MEDIUM", "LOW"}:
        return raw
    if "HIGH" in raw or "CRIT" in raw:
        return "HIGH"
    if "MED" in raw:
        return "MEDIUM"
    if "LOW" in raw:
        return "LOW"
    return "MEDIUM"


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\-.]+", "_", name.strip())[:80]
    return cleaned or "contract"


def _parse_clause_results(clause_results_json: str) -> list[dict[str, Any]]:
    data = json.loads(clause_results_json)
    if not isinstance(data, list):
        raise ValueError("clause_results_json must be a JSON array")

    normalized: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        findings = item.get("findings") or []
        if isinstance(findings, str):
            findings = [findings]
        normalized.append(
            {
                "clause": str(item.get("clause", "Unknown")),
                "risk": _normalize_risk(str(item.get("risk", "MEDIUM"))),
                "explanation": str(item.get("explanation", "")).strip(),
                "findings": [str(f).strip() for f in findings if str(f).strip()],
            }
        )
    return normalized


def generate_risk_report(
    contract_name: str,
    overall_risk: str,
    overall_explanation: str,
    clause_results_json: str,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Generate a PDF risk report for a contract assessment.

    Args:
        contract_name: Short display name of the contract.
        overall_risk: Overall decision — HIGH, MEDIUM, or LOW.
        overall_explanation: Why the overall risk rating was assigned.
        clause_results_json: JSON array of clause assessments. Each object should
            include `clause`, `risk`, `explanation`, and optional `findings`.
        tool_context: Optional ADK tool context (session state / artifacts).

    Returns:
        Status dict with the PDF path and summarized risk data.
    """
    try:
        clauses = _parse_clause_results(clause_results_json)
    except (json.JSONDecodeError, ValueError) as exc:
        return {"status": "error", "error_message": f"Invalid clause_results_json: {exc}"}

    if not clauses:
        return {
            "status": "error",
            "error_message": "clause_results_json contained no clause assessments.",
        }

    overall = _normalize_risk(overall_risk)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"risk_report_{_safe_filename(contract_name)}_{stamp}.pdf"
    output_path = REPORTS_DIR / filename

    _write_pdf(
        output_path=output_path,
        contract_name=contract_name or "Unnamed Contract",
        overall_risk=overall,
        overall_explanation=overall_explanation or "",
        clauses=clauses,
    )

    if tool_context is not None and hasattr(tool_context, "state"):
        tool_context.state["latest_risk_report_path"] = str(output_path)
        tool_context.state["latest_overall_risk"] = overall

    return {
        "status": "success",
        "report_path": str(output_path),
        "overall_risk": overall,
        "clauses_assessed": len(clauses),
        "message": f"Risk report written to {output_path}",
    }


def _write_pdf(
    output_path: Path,
    contract_name: str,
    overall_risk: str,
    overall_explanation: str,
    clauses: list[dict[str, Any]],
) -> None:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCenter",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    heading = ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        spaceBefore=14,
        spaceAfter=8,
        textColor=colors.HexColor("#101828"),
    )
    body = ParagraphStyle(
        "BodyJust",
        parent=styles["BodyText"],
        alignment=TA_JUSTIFY,
        leading=14,
        spaceAfter=6,
    )
    meta = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        textColor=colors.HexColor("#475467"),
        alignment=TA_CENTER,
        spaceAfter=18,
    )
    risk_style = ParagraphStyle(
        "OverallRisk",
        parent=styles["Heading2"],
        alignment=TA_CENTER,
        textColor=_RISK_COLORS.get(overall_risk, colors.black),
        spaceAfter=10,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=f"Contract Risk Report — {contract_name}",
    )

    story: list[Any] = [
        Paragraph("Contract Risk Assessment Report", title_style),
        Paragraph(
            f"<b>Contract:</b> {contract_name}<br/>"
            f"<b>Generated (UTC):</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
            meta,
        ),
        Paragraph(f"Overall Decision: {overall_risk}", risk_style),
        Paragraph(overall_explanation.replace("\n", "<br/>"), body),
        Paragraph("Clause-by-Clause Findings", heading),
    ]

    table_data = [
        [
            Paragraph("<b>Clause</b>", body),
            Paragraph("<b>Risk</b>", body),
            Paragraph("<b>Explanation</b>", body),
        ]
    ]
    for item in clauses:
        explanation = item["explanation"].replace("\n", "<br/>")
        if item["findings"]:
            bullets = "".join(f"<br/>• {f}" for f in item["findings"])
            explanation = f"{explanation}{bullets}"
        table_data.append(
            [
                Paragraph(item["clause"], body),
                Paragraph(f"<b>{item['risk']}</b>", body),
                Paragraph(explanation, body),
            ]
        )

    table = Table(table_data, colWidths=[1.4 * inch, 0.8 * inch, 4.3 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D5DD")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.3 * inch))
    story.append(
        Paragraph(
            "This report is generated by the Checker agent for internal legal review. "
            "It does not replace formal legal counsel sign-off.",
            meta,
        )
    )
    doc.build(story)
