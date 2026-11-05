"""Regression assertions for critical shell commands in deployment workflows."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkflowContractTests(unittest.TestCase):
    def test_private_oversight_runs_before_encryption_without_publication(self):
        workflow = (ROOT / ".github/workflows/brief-pilot.yml").read_text(encoding="utf-8")
        self.assertIn("python -m scripts.build_brief_oversight", workflow)
        self.assertLess(workflow.index("python -m scripts.build_brief_oversight"),
                        workflow.index("Encrypt model output and linked coverage metadata"))
        self.assertIn("permissions:\n      contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("deploy-pages", workflow)

    def test_shadow_research_invocation_uses_three_real_cli_arguments(self):
        workflow = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
        self.assertRegex(
            workflow,
            re.compile(
                r'python -m marketsignal investigate-archive \\\n'
                r'\s+--archive-file "data/archive/\$\(date -u \+%F\)\.json" \\\n'
                r'\s+--max-candidates 3 > shadow-research\.json'
            ),
        )
        self.assertIn("needs: collect", workflow)
        self.assertIn("publication_enabled", (ROOT / "marketsignal/newsroom.py").read_text())

    def test_shadow_workflow_has_no_write_permission_or_deployment(self):
        workflow = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
        shadow = workflow.split("\n  shadow:\n", 1)[1]
        self.assertIn("contents: read", shadow)
        self.assertNotIn("contents: write", shadow)
        self.assertNotIn("deploy-pages", shadow)
        self.assertNotIn("git push", shadow)


if __name__ == "__main__":
    unittest.main()
