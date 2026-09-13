"""Domain objects shared by collectors, analyzers, and renderers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Evidence:
    """One observed signal with its origin retained for auditability."""

    name: str
    value: Any
    source: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Evidence":
        return cls(
            name=str(payload["name"]),
            value=payload.get("value"),
            source=str(payload["source"]),
        )

    def label(self) -> str:
        return f"{self.name}={self.value} ({self.source})"


@dataclass(frozen=True)
class Incident:
    """An investigation request and the evidence available at analysis time."""

    incident_id: str
    symptom: str
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Incident":
        evidence = tuple(
            Evidence.from_dict(item) for item in payload.get("evidence", [])
        )
        names = [item.name for item in evidence]
        if len(names) != len(set(names)):
            raise ValueError("duplicate evidence signal names are not allowed")

        return cls(
            incident_id=str(payload["incident_id"]),
            symptom=str(payload["symptom"]),
            evidence=evidence,
        )

    def observations(self) -> dict[str, Evidence]:
        return {item.name: item for item in self.evidence}


@dataclass(frozen=True)
class Hypothesis:
    """A possible root cause with explicit supporting evidence."""

    title: str
    confidence: float
    explanation: str
    evidence: tuple[Evidence, ...]
    next_checks: tuple[str, ...]
    safe_actions: tuple[str, ...]


@dataclass(frozen=True)
class IncidentReport:
    """Ranked analysis result or an explicit statement of uncertainty."""

    incident_id: str
    status: str
    hypotheses: tuple[Hypothesis, ...] = field(default_factory=tuple)
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
