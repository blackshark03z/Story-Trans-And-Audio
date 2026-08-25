from __future__ import annotations

import unittest
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
        self.assertEqual(source, "contract")
        self.assertIn(
            (
                "project:test",
                "test",
                [
                    project_ci.sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-v",
                ],
            ),
            checks,
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


if __name__ == "__main__":
    unittest.main()
