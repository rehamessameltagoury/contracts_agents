# Contract Risk Assessment — Multi-Agent System (Google ADK 2)

Python multi-agent system that reviews commercial contracts against risk guidelines and produces a PDF risk report with an overall **HIGH / MEDIUM / LOW** decision.

## Architecture

```
orchestrator (root)
└── checker_agent (SequentialAgent)
    ├── clause_review_team (ParallelAgent)
    │   ├── liability_clause_agent
    │   ├── termination_clause_agent
    │   ├── intellectual_property_clause_agent
    │   └── operational_business_clause_agent
    └── checker_synthesizer  →  generate_risk_report (PDF tool)
```

More specialists can be added later under `orchestrator.sub_agents`.

## Setup

1. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and set your API key:

```env
GOOGLE_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3-flash
```

3. Guidelines PDF lives at:

`contracts_risk_assessment/guidelines/contract_risk_guidelines.pdf`

You can replace that file, or attach a guidelines PDF when chatting with the agent. Prompts include an **ATTACHMENT SLOT** so attached guidelines take priority.

## Editable prompts

All agent instructions are plain text files under `contracts_risk_assessment/prompts/`:

| File | Agent |
|------|--------|
| `orchestrator.txt` | Root orchestrator |
| `checker.txt` | Checker synthesizer (combine + PDF) |
| `liability_clause.txt` | Liability assessor |
| `termination_clause.txt` | Termination assessor |
| `intellectual_property_clause.txt` | IP assessor |
| `operational_business_clause.txt` | Operational & Business assessor |

Edit these files anytime — no code changes required for prompt tweaks. Restart `adk web` / `adk run` after edits.

## Run

From the repo root:

```bash
adk web .
```

Or:

```bash
adk run contracts_risk_assessment
```

Attach or paste a contract, ask for a risk assessment, and the orchestrator will route to the Checker. PDF reports are written to `output/reports/`.

## Example ask

> Assess this contract for legal risk against our guidelines. Produce a PDF report.

## Performance testing (before adding more agents)

1. Copy `.env.example` → `.env` and set `GOOGLE_API_KEY`.
2. Run the timed Checker benchmark against a known high-risk sample contract:

```bash
python scripts/benchmark_checker.py
python scripts/benchmark_checker.py --runs 3
```

This prints latency (min/mean/max), PDF success rate, and whether overall risk is **HIGH** for the fixture. Results are saved under `output/benchmarks/`.

3. Optional ADK eval (trajectory + response quality):

```bash
adk eval contracts_risk_assessment tests/eval/checker_high_risk.test.json
```

Interactive trace inspection:

```bash
adk web .
```

## Notes

- Model and API key come only from environment variables (`GEMINI_MODEL`, `GOOGLE_API_KEY`).
- Guideline CRITICAL ratings are mapped to **HIGH** in the High/Medium/Low scale, with CRITICAL noted in the explanation.
- The Checker is the first specialist; wire additional agents next to `checker_agent` in `agent.py`.
