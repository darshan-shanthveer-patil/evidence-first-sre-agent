import contextlib
import io
import json
from pathlib import Path
import unittest

from sre_agent.cli import main


FIXTURES = Path(__file__).parents[1] / "examples" / "incidents"


class CliTests(unittest.TestCase):
    def test_reports_gaps_for_both_diagnosed_and_inconclusive_incidents(self):
        for filename, status in (("telemetry-gaps.json", "inconclusive"), ("partial-oom.json", "diagnosed")):
            with self.subTest(filename=filename):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    main([str(FIXTURES / filename)])
                self.assertIn(f"Status: {status}", output.getvalue())
                self.assertIn("Evidence limitations", output.getvalue())
                self.assertIn("logs.errors: unavailable (loki)", output.getvalue())

    def test_json_preserves_each_collection_outcome(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main([str(FIXTURES / "telemetry-gaps.json"), "--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual("inconclusive", payload["status"])
        self.assertEqual([], payload["hypotheses"])
        self.assertEqual(
            {"stale", "empty", "truncated", "unavailable"},
            {item["status"] for item in payload["evidence_coverage"]},
        )

    def test_prints_human_readable_report(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([str(FIXTURES / "service-selector-mismatch.json")])

        self.assertEqual(0, result)
        self.assertIn("Confidence: 96%", output.getvalue())
        self.assertIn("Safe actions:", output.getvalue())
        self.assertIn("Validate endpoints are populated", output.getvalue())

    def test_prints_json_report(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([str(FIXTURES / "oomkilled.json"), "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual("diagnosed", payload["status"])
        self.assertEqual("inc-2026-001", payload["incident_id"])


if __name__ == "__main__":
    unittest.main()
