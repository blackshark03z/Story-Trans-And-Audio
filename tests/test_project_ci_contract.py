from __future__ import annotations

import unittest
import json
from pathlib import Path

from scripts import project_ci


ROOT = Path(__file__).resolve().parents[1]


class ProjectCiContractTests(unittest.TestCase):
    def test_project_contract_commands_are_raw_argv(self) -> None:
        contract = project_ci.project_contract(ROOT)

        self.assertNotIn("`", contract["Install command"])
        self.assertNotIn("`", contract["Test command"])
        self.assertEqual(
            project_ci.install_command(ROOT),
            [project_ci.sys.executable, "-m", "pip", "install", "-e", "."],
        )

        checks, source = project_ci.checks(ROOT)
        self.assertEqual(source, "buildos-policy")
        policy = json.loads((ROOT / ".buildos-policy.json").read_text(encoding="utf-8"))
        expected = [
            (
                f"buildos:{gate['id']}",
                "test",
                [project_ci.sys.executable, *gate["argv"][1:]],
            )
            for gate in policy["project_lifecycle"]["quality_gates"]
        ]
        self.assertEqual(
            checks,
            expected,
        )

    def test_markdown_delimiters_are_not_silently_reinterpreted(self) -> None:
        self.assertEqual(
            project_ci._cmd("`python -m pip install -e .`"),
            ["`python", "-m", "pip", "install", "-e", ".`"],
        )

    def test_declared_python_is_bound_to_ci_interpreter(self) -> None:
        self.assertEqual(
            project_ci._cmd("python -m unittest tests.test_project_ci_contract"),
            [
                project_ci.sys.executable,
                "-m",
                "unittest",
                "tests.test_project_ci_contract",
            ],
        )

    def test_windows_policy_python_is_bound_to_ci_interpreter(self) -> None:
        self.assertEqual(
            project_ci._bind_python(
                [r"D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe", "-m", "unittest"]
            ),
            [project_ci.sys.executable, "-m", "unittest"],
        )

    def test_inline_browser_probes_use_shared_timeout_boundary(self) -> None:
        browser_tests = (
            ROOT / "tests" / "test_assignment_completed_review_browser.py",
            ROOT / "tests" / "test_daily_use_v2a_browser.py",
            ROOT / "tests" / "test_sidebar_navigation_browser.py",
        )
        for path in browser_tests:
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"Date\.now\(\)\s*\+\s*\d+")
            self.assertIn("browser_acceptance_runtime.cjs", source)
            self.assertIn("boundedBrowserTimeout(", source)


if __name__ == "__main__":
    unittest.main()
