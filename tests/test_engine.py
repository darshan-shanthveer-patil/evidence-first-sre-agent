import unittest

from sre_agent import Evidence, Incident, IncidentAnalyzer


def incident(*evidence: Evidence) -> Incident:
    return Incident("test-incident", "test symptom", evidence)


class IncidentAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = IncidentAnalyzer()

    def test_identifies_oom_kill(self) -> None:
        report = self.analyzer.analyze(
            incident(
                Evidence("workload.container_last_state.reason", "OOMKilled", "kubernetes"),
                Evidence("container.memory_working_set_pct_limit", 99, "prometheus"),
            )
        )

        self.assertEqual("diagnosed", report.status)
        self.assertIn("memory limit", report.hypotheses[0].title)
        self.assertEqual(0.98, report.hypotheses[0].confidence)

    def test_distinguishes_selector_mismatch_from_unready_pods(self) -> None:
        report = self.analyzer.analyze(
            incident(
                Evidence("service.endpoint_count", 0, "kubernetes"),
                Evidence("service.selector_match_count", 0, "kubernetes"),
                Evidence("workload.ready_pod_count", 0, "kubernetes"),
            )
        )

        self.assertEqual("inconclusive", report.status)

    def test_requires_latency_breach_and_throttling_for_cpu_diagnosis(self) -> None:
        report = self.analyzer.analyze(
            incident(
                Evidence("container.cpu_utilization_pct", 97, "prometheus"),
                Evidence("container.cpu_throttled_seconds_rate", 0, "prometheus"),
                Evidence("http.latency_p90_ms", 900, "prometheus"),
                Evidence("http.latency_slo_ms", 500, "service-catalog"),
            )
        )

        self.assertEqual("inconclusive", report.status)

    def test_ranks_stronger_hypothesis_first(self) -> None:
        report = self.analyzer.analyze(
            incident(
                Evidence("workload.container_last_state.reason", "OOMKilled", "kubernetes"),
                Evidence("pod.waiting_reason", "CrashLoopBackOff", "kubernetes"),
                Evidence("workload.restart_count", 6, "kubernetes"),
            )
        )

        self.assertEqual(2, len(report.hypotheses))
        self.assertGreater(
            report.hypotheses[0].confidence,
            report.hypotheses[1].confidence,
        )

    def test_reports_missing_evidence_when_inconclusive(self) -> None:
        report = self.analyzer.analyze(incident(Evidence("pod.phase", "Running", "kubernetes")))

        self.assertEqual("inconclusive", report.status)
        self.assertIn("service.endpoint_count", report.missing_evidence)


if __name__ == "__main__":
    unittest.main()

