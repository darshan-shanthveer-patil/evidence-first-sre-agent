"""Deterministic diagnosis rules for the first project milestone."""

from __future__ import annotations

from collections.abc import Callable

from .models import Evidence, Hypothesis, Incident, IncidentReport


Rule = Callable[[dict[str, Evidence]], Hypothesis | None]


class IncidentAnalyzer:
    """Rank evidence-backed hypotheses without mutating infrastructure."""

    def __init__(self) -> None:
        self._rules: tuple[Rule, ...] = (
            self._oom_killed,
            self._selector_mismatch,
            self._probe_failure,
            self._crash_loop,
            self._cpu_saturation,
        )

    def analyze(self, incident: Incident) -> IncidentReport:
        observations = incident.observations()
        hypotheses = tuple(
            sorted(
                (
                    result
                    for rule in self._rules
                    if (result := rule(observations)) is not None
                ),
                key=lambda item: item.confidence,
                reverse=True,
            )
        )

        if hypotheses:
            return IncidentReport(
                incident_id=incident.incident_id,
                status="diagnosed",
                hypotheses=hypotheses,
            )

        useful_signals = (
            "workload.container_last_state.reason",
            "pod.waiting_reason",
            "workload.restart_count",
            "service.endpoint_count",
            "service.selector_match_count",
            "workload.ready_pod_count",
            "http.probe_success",
            "container.cpu_utilization_pct",
            "container.cpu_throttled_seconds_rate",
            "http.latency_p90_ms",
            "http.latency_slo_ms",
        )
        missing = tuple(name for name in useful_signals if name not in observations)
        return IncidentReport(
            incident_id=incident.incident_id,
            status="inconclusive",
            missing_evidence=missing,
        )

    @staticmethod
    def _oom_killed(observations: dict[str, Evidence]) -> Hypothesis | None:
        reason = observations.get("workload.container_last_state.reason")
        if reason is None or reason.value != "OOMKilled":
            return None

        supporting = [reason]
        memory = observations.get("container.memory_working_set_pct_limit")
        restarts = observations.get("workload.restart_count")
        if memory is not None:
            supporting.append(memory)
        if restarts is not None:
            supporting.append(restarts)

        confidence = 0.98 if memory and _number(memory.value) >= 95 else 0.92
        return Hypothesis(
            title="The container was terminated after exceeding its memory limit.",
            confidence=confidence,
            explanation=(
                "Kubernetes reported OOMKilled as the previous container state. "
                "Memory pressure and restart evidence strengthen the diagnosis."
            ),
            evidence=tuple(supporting),
            next_checks=(
                "Compare the working set with the configured memory limit before termination.",
                "Check whether traffic, cache growth, or a deployment changed memory demand.",
            ),
            safe_actions=(
                "Capture a heap profile or workload-specific memory diagnostics.",
                "Change limits only after validating normal and peak memory usage.",
            ),
        )

    @staticmethod
    def _selector_mismatch(observations: dict[str, Evidence]) -> Hypothesis | None:
        endpoints = observations.get("service.endpoint_count")
        matches = observations.get("service.selector_match_count")
        ready = observations.get("workload.ready_pod_count")
        if not (
            endpoints
            and matches
            and ready
            and _number(endpoints.value) == 0
            and _number(matches.value) == 0
            and _number(ready.value) > 0
        ):
            return None

        return Hypothesis(
            title="The Service selector does not match the ready workload pods.",
            confidence=0.96,
            explanation=(
                "The Service has no endpoints and its selector matches no pods, while "
                "the workload still has ready pods."
            ),
            evidence=(endpoints, matches, ready),
            next_checks=(
                "Diff the Service selector against labels on the ready pods.",
                "Check whether a recent deployment changed workload labels.",
            ),
            safe_actions=(
                "Patch the selector only after confirming the intended backend labels.",
                "Validate endpoints are populated before sending production traffic.",
            ),
        )

    @staticmethod
    def _probe_failure(observations: dict[str, Evidence]) -> Hypothesis | None:
        probe = observations.get("http.probe_success")
        ready = observations.get("pod.ready")
        if not (probe and ready and not _truthy(probe.value) and not _truthy(ready.value)):
            return None

        status = observations.get("http.probe_status_code")
        supporting = (probe, ready) + ((status,) if status else ())
        return Hypothesis(
            title="The configured health probe is failing.",
            confidence=0.91,
            explanation="Probe failure coincides with the pod being marked unready.",
            evidence=supporting,
            next_checks=(
                "Run the probe request from inside the pod network namespace.",
                "Compare the probe path, port, scheme, and timeout with the application listener.",
            ),
            safe_actions=(
                "Correct the probe only after verifying the application's real health endpoint.",
                "Keep readiness failure isolated from liveness restart behavior.",
            ),
        )

    @staticmethod
    def _crash_loop(observations: dict[str, Evidence]) -> Hypothesis | None:
        reason = observations.get("pod.waiting_reason")
        restarts = observations.get("workload.restart_count")
        if not (
            reason
            and restarts
            and reason.value == "CrashLoopBackOff"
            and _number(restarts.value) >= 2
        ):
            return None

        exit_code = observations.get("workload.last_exit_code")
        supporting = (reason, restarts) + ((exit_code,) if exit_code else ())
        return Hypothesis(
            title="The workload is repeatedly exiting during startup or execution.",
            confidence=0.90,
            explanation="CrashLoopBackOff and repeated restarts establish a recurring process failure.",
            evidence=supporting,
            next_checks=(
                "Inspect previous-container logs and the termination message.",
                "Compare command, configuration, and secret changes with the last healthy revision.",
            ),
            safe_actions=(
                "Reproduce the failing command against a non-production workload.",
                "Roll back only when a known-good revision and rollback impact are confirmed.",
            ),
        )

    @staticmethod
    def _cpu_saturation(observations: dict[str, Evidence]) -> Hypothesis | None:
        utilization = observations.get("container.cpu_utilization_pct")
        throttling = observations.get("container.cpu_throttled_seconds_rate")
        latency = observations.get("http.latency_p90_ms")
        slo = observations.get("http.latency_slo_ms")
        if not (
            utilization
            and throttling
            and latency
            and slo
            and _number(utilization.value) >= 90
            and _number(throttling.value) > 0
            and _number(latency.value) > _number(slo.value)
        ):
            return None

        return Hypothesis(
            title="CPU saturation is contributing to the latency breach.",
            confidence=0.88,
            explanation=(
                "High CPU utilization and throttling coincide with p90 latency above "
                "the declared service objective."
            ),
            evidence=(utilization, throttling, latency, slo),
            next_checks=(
                "Correlate throttling and latency over the same interval and pod set.",
                "Inspect CPU requests, limits, HPA behavior, and per-route workload demand.",
            ),
            safe_actions=(
                "Load-test proposed resource or autoscaling changes before production rollout.",
                "Confirm downstream latency is not the dominant contributor.",
            ),
        )


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)
