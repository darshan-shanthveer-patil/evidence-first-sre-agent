"""Command-line entry point for analyzing captured incident evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .engine import IncidentAnalyzer
from .models import Incident, IncidentReport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sre-agent",
        description="Rank evidence-backed hypotheses for a captured incident.",
    )
    parser.add_argument("incident", type=Path, help="Path to an incident JSON file")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def load_incident(path: Path) -> Incident:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("incident document must be a JSON object")
    return Incident.from_dict(payload)


def render_text(report: IncidentReport) -> str:
    lines = [f"Incident: {report.incident_id}", f"Status: {report.status}"]
    if report.status == "inconclusive":
        lines.append("Missing evidence:")
        lines.extend(f"- {item}" for item in report.missing_evidence)
        return "\n".join(lines)

    for index, hypothesis in enumerate(report.hypotheses, start=1):
        lines.extend(
            [
                "",
                f"{index}. {hypothesis.title}",
                f"   Confidence: {hypothesis.confidence:.0%}",
                f"   Why: {hypothesis.explanation}",
                "   Evidence:",
                *(f"   - {item.label()}" for item in hypothesis.evidence),
                "   Next checks:",
                *(f"   - {item}" for item in hypothesis.next_checks),
                "   Safe actions:",
                *(f"   - {item}" for item in hypothesis.safe_actions),
            ]
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        incident = load_incident(args.incident)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise SystemExit(f"unable to load incident: {error}") from error

    report = IncidentAnalyzer().analyze(incident)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_text(report))
    return 0

