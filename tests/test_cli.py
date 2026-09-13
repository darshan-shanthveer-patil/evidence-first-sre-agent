import contextlib
import io
import json
from pathlib import Path
import unittest

from sre_agent.cli import main


FIXTURES = Path(__file__).parents[1] / "examples" / "incidents"


class CliTests(unittest.TestCase):
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

