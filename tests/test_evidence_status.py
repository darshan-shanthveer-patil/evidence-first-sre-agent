"""Collection failures must not become positive evidence of an incident."""

import json
from pathlib import Path
import unittest

from sre_agent import Evidence, Incident, IncidentAnalyzer


FIXTURES = Path(__file__).parents[1] / "examples" / "incidents"
UNUSABLE = ("unavailable", "empty", "stale", "truncated")


class EvidenceStatusTests(unittest.TestCase):
    def test_legacy_evidence_defaults_to_available(self):
        evidence = Evidence.from_dict({"name": "count", "value": 0, "source": "test"})
        self.assertEqual("available", evidence.status)
        self.assertEqual(0, evidence.value)

    def test_rejects_unknown_status_and_available_null(self):
        for status in ("unknown", "AVAILABLE", None, [], {}):
            with self.subTest(status=status), self.assertRaises(ValueError):
                Evidence("count", 0, "test", status=status)
        with self.assertRaisesRegex(ValueError, "non-null"):
            Evidence.from_dict({"name": "count", "source": "test"})

    def test_unusable_required_evidence_blocks_each_diagnosis(self):
        required = {
            "oomkilled.json": "workload.container_last_state.reason",
            "crash-loop.json": "workload.restart_count",
            "cpu-saturation.json": "container.cpu_utilization_pct",
            "service-selector-mismatch.json": "service.endpoint_count",
            "probe-failure.json": "http.probe_success",
        }
        for filename, signal in required.items():
            for status in UNUSABLE:
                with self.subTest(fixture=filename, status=status):
                    payload = json.loads((FIXTURES / filename).read_text())
                    for item in payload["evidence"]:
                        if item["name"] == signal:
                            item["status"] = status
                    report = IncidentAnalyzer().analyze(Incident.from_dict(payload))
                    self.assertEqual("inconclusive", report.status)
                    self.assertIn(signal, report.missing_evidence)
                    coverage = {item.name: item.status for item in report.evidence_coverage}
                    self.assertEqual(status, coverage[signal])

    def test_independent_available_evidence_still_supports_diagnosis(self):
        report = IncidentAnalyzer().analyze(Incident("partial", "restarts", (
            Evidence("workload.container_last_state.reason", "OOMKilled", "kubernetes"),
            Evidence("container.memory_working_set_pct_limit", 99, "prometheus", "stale"),
            Evidence("logs.errors", None, "loki", "unavailable"),
        )))
        self.assertEqual("diagnosed", report.status)
        self.assertEqual(0.92, report.hypotheses[0].confidence)
        self.assertEqual(1, len(report.hypotheses[0].evidence))
        self.assertEqual(3, len(report.evidence_coverage))
        self.assertEqual("unavailable", report.to_dict()["evidence_coverage"][2]["status"])

    def test_successful_empty_query_is_not_a_measured_zero(self):
        for status in ("empty", "available"):
            with self.subTest(status=status):
                report = IncidentAnalyzer().analyze(Incident("empty", "no traffic", (
                    Evidence("service.endpoint_count", 0, "kubernetes", status),
                    Evidence("service.selector_match_count", 0, "kubernetes"),
                    Evidence("workload.ready_pod_count", 2, "kubernetes"),
                )))
                self.assertEqual("diagnosed" if status == "available" else "inconclusive", report.status)

    def test_malformed_values_do_not_become_zero_or_false(self):
        for value in ("", "timeout", [], {}, float("nan"), float("inf")):
            with self.subTest(value=value):
                analyzer = IncidentAnalyzer()
                selector = analyzer.analyze(Incident("invalid-count", "no traffic", (
                    Evidence("service.endpoint_count", value, "kubernetes"),
                    Evidence("service.selector_match_count", 0, "kubernetes"),
                    Evidence("workload.ready_pod_count", 2, "kubernetes"),
                )))
                probe = analyzer.analyze(Incident("invalid-probe", "probe unknown", (
                    Evidence("http.probe_success", value, "probe"),
                    Evidence("pod.ready", False, "kubernetes"),
                )))
                self.assertEqual("inconclusive", selector.status)
                self.assertEqual("inconclusive", probe.status)


if __name__ == "__main__":
    unittest.main()
