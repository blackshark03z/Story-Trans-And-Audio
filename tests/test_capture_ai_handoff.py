import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_ai_handoff.ps1"


def find_powershell():
    for name in ("pwsh", "powershell"):
        path = shutil.which(name)
        if path:
            return path
    return None


POWERSHELL = find_powershell()


@unittest.skipIf(POWERSHELL is None, "PowerShell executable not found")
class CaptureAiHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo with spaces"
        self.handoff = self.base / "handoff with spaces"
        self.repo.mkdir()
        self._git("init")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Test User")
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "AI_ACTIVE_TASK_TEMPLATE.md").write_text(
            "# Template\n\nManual template body\n", encoding="utf-8"
        )
        (self.repo / "story.txt").write_text("one\n", encoding="utf-8")
        self._git("add", "docs/AI_ACTIVE_TASK_TEMPLATE.md", "story.txt")
        self._git("commit", "-m", "Initial commit")
        self.head = self._git("rev-parse", "HEAD").stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *args, check=True):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def _run_script(self, *extra, check=True):
        cmd = [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RepositoryPath",
            str(self.repo),
            "-HandoffRoot",
            str(self.handoff),
            "-UpdatedBy",
            "unit-test",
            "-TechLeadModel",
            "UNVERIFIED",
            "-WorkerIdentity",
            "UNVERIFIED",
            *extra,
        ]
        return subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def _active(self, name):
        return self.handoff / name

    def _read_all_active(self):
        text = ""
        for path in self.handoff.glob("*"):
            if path.is_file():
                text += path.read_text(encoding="utf-8", errors="replace")
        return text

    def test_clean_repo_capture_creates_active_files_and_git_metadata(self):
        result = self._run_script("-ExpectedHead", self.head)

        self.assertIn("SUCCESS", result.stdout)
        self.assertTrue(self._active("ACTIVE_TASK.md").exists())
        self.assertTrue(self._active("GIT_STATE.txt").exists())
        self.assertTrue(self._active("LAST_TEST_RESULT.txt").exists())
        self.assertTrue(self._active("ACTIVE_WORKTREE.patch").exists())
        task = self._active("ACTIVE_TASK.md").read_text(encoding="utf-8")
        git_state = self._active("GIT_STATE.txt").read_text(encoding="utf-8")
        self.assertIn("<!-- AI-HANDOFF-AUTO-START -->", task)
        self.assertIn("Manual template body", task)
        self.assertIn(self.head, git_state)
        self.assertIn("Initial commit", git_state)
        self.assertIn("ExpectedHead check: matched", git_state)
        self.assertEqual("", self._active("ACTIVE_WORKTREE.patch").read_text(encoding="utf-8"))

    def test_safe_tracked_modification_produces_usable_patch(self):
        (self.repo / "story.txt").write_text("one\ntwo\n", encoding="utf-8")
        self._run_script()

        patch = self._active("ACTIVE_WORKTREE.patch")
        self.assertIn("+two", patch.read_text(encoding="utf-8"))
        clone = self.base / "clone"
        subprocess.run(["git", "clone", str(self.repo), str(clone)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(clone), "reset", "--hard", self.head], check=True, stdout=subprocess.PIPE)
        applied = subprocess.run(
            ["git", "-C", str(clone), "apply", "--check", str(patch)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(0, applied.returncode, applied.stderr)

    def test_staged_and_unstaged_tracked_changes_are_captured(self):
        (self.repo / "story.txt").write_text("one\nstaged\n", encoding="utf-8")
        self._git("add", "story.txt")
        (self.repo / "story.txt").write_text("one\nstaged\nunstaged\n", encoding="utf-8")

        self._run_script()

        patch = self._active("ACTIVE_WORKTREE.patch").read_text(encoding="utf-8")
        self.assertIn("+staged", patch)
        self.assertIn("+unstaged", patch)

    def test_untracked_filenames_listed_without_contents(self):
        (self.repo / "new secret notes.txt").write_text("UNTRACKED_SECRET_VALUE", encoding="utf-8")

        self._run_script()

        all_active = self._read_all_active()
        self.assertIn("new secret notes.txt", all_active)
        self.assertNotIn("UNTRACKED_SECRET_VALUE", all_active)

    def test_manual_active_task_preserved_and_later_capture_replaces_only_managed_block(self):
        self.handoff.mkdir()
        active = self._active("ACTIVE_TASK.md")
        active.write_text("Manual heading\nManual body\n", encoding="utf-8")

        self._run_script("-CurrentTask", "First")
        first = active.read_text(encoding="utf-8")
        self.assertIn("Manual heading\nManual body", first)
        self.assertIn("Current task: `First", first)

        self._run_script("-CurrentTask", "Second")
        second = active.read_text(encoding="utf-8")
        self.assertIn("Manual heading\nManual body", second)
        self.assertIn("Current task: `Second", second)
        self.assertNotIn("Current task: `First", second)
        history_dirs = list((self.handoff / "HISTORY").iterdir())
        self.assertGreaterEqual(len(history_dirs), 1)

    def test_expected_head_mismatch_fails_without_overwrite(self):
        self._run_script("-CurrentTask", "Preserve me")
        before = self._active("ACTIVE_TASK.md").read_text(encoding="utf-8")

        result = self._run_script("-ExpectedHead", "0" * 40, "-CurrentTask", "Do not write", check=False)

        self.assertNotEqual(0, result.returncode)
        after = self._active("ACTIVE_TASK.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertIn("ExpectedHead mismatch", result.stderr)

    def test_suspicious_secret_withholds_patch_and_removes_previous_patch(self):
        (self.repo / "story.txt").write_text("one\nsafe\n", encoding="utf-8")
        self._run_script()
        self.assertTrue(self._active("ACTIVE_WORKTREE.patch").exists())

        fake_secret = "sk-testFakeSecretValue1234567890"
        (self.repo / "story.txt").write_text(f"one\napi_key={fake_secret}\n", encoding="utf-8")
        result = self._run_script(check=True)

        self.assertFalse(self._active("ACTIVE_WORKTREE.patch").exists())
        self.assertTrue(self._active("ACTIVE_WORKTREE.patch.status").exists())
        all_active = self._read_all_active()
        self.assertIn("WITHHELD_SUSPECTED_SECRET", all_active)
        self.assertIn("API_KEY", all_active)
        self.assertNotIn(fake_secret, all_active)
        self.assertNotIn(fake_secret, result.stdout)
        self.assertNotIn(fake_secret, result.stderr)

    def test_last_test_result_uses_only_explicit_summary(self):
        (self.repo / "ignored.log").write_text("terminal history should not be scraped", encoding="utf-8")

        self._run_script(
            "-LastTestCommand",
            "python -m unittest",
            "-LastTestStatus",
            "PASS",
            "-LastTestSummary",
            "3 tests passed",
            "-LastTestDuration",
            "1s",
        )

        text = self._active("LAST_TEST_RESULT.txt").read_text(encoding="utf-8")
        self.assertIn("python -m unittest", text)
        self.assertIn("PASS", text)
        self.assertIn("3 tests passed", text)
        self.assertIn("1s", text)
        self.assertNotIn("terminal history", text)

    def test_git_state_unchanged_and_no_repo_files_created_by_script(self):
        before_head = self._git("rev-parse", "HEAD").stdout
        before_branch = self._git("branch", "--show-current").stdout
        before_status = self._git("status", "--porcelain=v1").stdout

        self._run_script()

        self.assertEqual(before_head, self._git("rev-parse", "HEAD").stdout)
        self.assertEqual(before_branch, self._git("branch", "--show-current").stdout)
        self.assertEqual(before_status, self._git("status", "--porcelain=v1").stdout)

    def test_history_snapshot_names_do_not_collide(self):
        self._run_script()
        for index in range(3):
            self._run_script("-CurrentPhase", f"phase {index}")

        names = [path.name for path in (self.handoff / "HISTORY").iterdir()]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 3)

    def test_invalid_repo_path_fails_safely(self):
        bad_repo = self.base / "missing"
        result = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-RepositoryPath",
                str(bad_repo),
                "-HandoffRoot",
                str(self.handoff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.handoff.exists())

    def test_missing_template_fails_without_partial_replacement(self):
        self._run_script("-CurrentTask", "Keep")
        before = self._active("ACTIVE_TASK.md").read_text(encoding="utf-8")

        missing = self.base / "missing-template.md"
        result = self._run_script("-TemplatePath", str(missing), "-CurrentTask", "No write", check=False)

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self._active("ACTIVE_TASK.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
