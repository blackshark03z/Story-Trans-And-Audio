#!/usr/bin/env python3
"""Windows compatibility acceptance for the installed, unmodified v1.16 kernel.

This is intentionally not a replacement for scripts/self_test_v116.py.  The
supplied test is retained unchanged; its quoted interpreter command cannot be
executed by its argv-mode runner on Windows.  This verifier changes only that
acceptance method and drives the installed kernel against throwaway fixtures.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


KERNEL_ROOT = Path(__file__).resolve().parents[2]
KERNEL = KERNEL_ROOT / "scripts" / "ai_os.py"
sys.path.insert(0, str(KERNEL_ROOT / "scripts"))
from evidence_support import sanitize_output  # noqa: E402


def run(root: Path, *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(KERNEL), "--root", str(root), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"{args!r} rc={result.returncode} expected={expect}\n"
            f"OUT={result.stdout}\nERR={result.stderr}"
        )
    return result


def command(root: Path, *args: str) -> None:
    subprocess.run(args, cwd=root, check=True, capture_output=True, text=True, timeout=20)


def fresh(base: Path, name: str) -> Path:
    root = base / name
    root.mkdir()
    for relative in (".ai", "config", "templates", "scripts"):
        shutil.copytree(KERNEL_ROOT / relative, root / relative, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # The repository's live pre-init files deliberately preserve Story Audio
    # facts and therefore are not generic init templates. Fixtures use the
    # installed v1.16 templates solely inside their disposable directory.
    shutil.copy2(KERNEL_ROOT / "templates" / "PROJECT_TEMPLATE.md", root / ".ai" / "PROJECT.md")
    shutil.copy2(KERNEL_ROOT / "templates" / "STATE_TEMPLATE.md", root / ".ai" / "STATE.md")
    command(root, "git", "init", "-q")
    command(root, "git", "config", "user.email", "v116@example.invalid")
    command(root, "git", "config", "user.name", "v116 acceptance")
    command(root, "git", "add", ".")
    command(root, "git", "commit", "-qm", "base")
    run(
        root,
        "init",
        "--project-id", "P",
        "--owner", "owner",
        "--problem", "problem",
        "--target-user", "user",
        "--primary-action", "action",
        "--observable-result", "result",
        "--mvp-goal", "goal",
    )
    command(root, "git", "add", ".")
    command(root, "git", "commit", "-qm", "init")
    return root


def test_namespace_and_lock(base: Path) -> None:
    root = fresh(base, "hardening")
    bad = run(root, "begin", "--task-id", "../../ESCAPE", "--outcome", "x", "--risk", "R0", "--success-criterion", "SC-001", "--delivery-delta", "NO_DELTA", "--modify", "src/x.py", expect=1)
    assert "Invalid task ID" in bad.stdout + bad.stderr
    assert not (root.parent / "ESCAPE").exists()
    bad = run(root, "goal", "begin", "--goal-id", "../../GOAL_ESCAPE", "--goal", "x", "--accept", "observable output", expect=1)
    assert "Invalid goal ID" in bad.stdout + bad.stderr
    assert not (root.parent / "GOAL_ESCAPE").exists()
    (root / ".ai" / ".lifecycle.lock").write_text("pid=99999999 started=1\n", encoding="utf-8")
    run(root, "begin", "--task-id", "LOCK1", "--outcome", "lock recovery", "--risk", "R0", "--success-criterion", "SC-001", "--delivery-delta", "NO_DELTA", "--modify", "docs/x.md")
    assert not (root / ".ai" / ".lifecycle.lock").exists()
    run(root, "abort")


def test_redaction() -> None:
    sample = """Authorization: Bearer abc.def.ghi
api_key=supersecret
eyJabcdefghij.abcdefghij.abcdefghij
ghp_abcdefghijklmnopqrstuvwxyz123456
-----BEGIN PRIVATE KEY-----
secret-body
-----END PRIVATE KEY-----
postgres://user:pass@example.com/db
"""
    redacted, _, _ = sanitize_output(sample)
    for secret in ("abc.def.ghi", "supersecret", "eyJabcdefghij", "ghp_abcdefghijklmnopqrstuvwxyz", "secret-body", "user:pass@"):
        assert secret not in redacted


def test_state_hazard_reuse_and_debug(base: Path) -> None:
    root = fresh(base, "state")
    run(root, "begin", "--task-id", "CSS1", "--outcome", "adjust button spacing", "--risk", "R0", "--success-criterion", "SC-001", "--delivery-delta", "NO_DELTA", "--modify", "styles/button.css")
    status = json.loads(run(root, "status", "--json").stdout)
    assert status["state_hazard"] == "S0"
    run(root, "abort")

    bad = run(root, "begin", "--task-id", "STATE1", "--outcome", "preserve dirty draft during polling refresh", "--risk", "R1", "--success-criterion", "SC-001", "--delivery-delta", "EXECUTABLE_CAPABILITY", "--modify", "src/state.py", expect=1)
    assert "minimal pre-code state contract" in bad.stdout + bad.stderr
    state_args = (
        "--state-authority", "persisted project.effects",
        "--state-transition", "SAVED -> EDIT -> DIRTY -> SAVE -> SAVED",
        "--state-invariant", "background refresh must not overwrite DIRTY",
        "--state-dependency", "src/state.py",
    )
    run(root, "begin", "--task-id", "STATE1", "--outcome", "preserve dirty draft during polling refresh", "--risk", "R1", "--success-criterion", "SC-001", "--delivery-delta", "EXECUTABLE_CAPABILITY", "--modify", "src/state.py", "--create", "src/state.py", *state_args)
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "state.py").write_text("def reconcile(dirty, local, remote):\n    return local if dirty else remote\n", encoding="utf-8")

    system32 = Path(os.environ["SystemRoot"]) / "System32"
    focused = (system32 / "whoami.exe").as_posix()
    transition = (system32 / "hostname.exe").as_posix()
    temporal = (system32 / "tasklist.exe").as_posix()
    assert all(Path(command).is_file() for command in (focused, transition, temporal))
    run(root, "done", "--outcome", "preserved dirty draft", "--focused-command", focused, "--state-transition-command", transition, "--state-temporal-command", temporal, "--output-inspected-by", "agent:windows-v116")
    first = json.loads((root / ".ai" / "evidence" / "STATE1" / "r001" / "manifest.json").read_text(encoding="utf-8"))
    first_proofs = [item for item in first["checks"] if item.get("kind") in {"state_transition", "state_temporal"}]
    assert first["state_hazard_level"] == "S3" and len(first_proofs) == 2 and not any(item.get("reused") for item in first_proofs), first

    run(root, "begin", "--task-id", "STATE2", "--outcome", "verify dirty draft during polling refresh", "--risk", "R1", "--success-criterion", "SC-001", "--delivery-delta", "NO_DELTA", "--modify", "src/state.py", *state_args)
    run(root, "done", "--outcome", "state contract still holds", "--focused-command", focused, "--state-transition-command", transition, "--state-temporal-command", temporal, "--output-inspected-by", "agent:windows-v116")
    second = json.loads((root / ".ai" / "evidence" / "STATE2" / "r001" / "manifest.json").read_text(encoding="utf-8"))
    reused = [item for item in second["checks"] if item.get("kind") in {"state_transition", "state_temporal"}]
    assert len(reused) == 2 and all(item.get("reused") is True for item in reused)

    run(root, "begin", "--task-id", "BUG1", "--outcome", "diagnose flaky UI verifier", "--risk", "R1", "--success-criterion", "SC-001", "--delivery-delta", "NO_DELTA", "--modify", "tests/ui.py")
    run(root, "debug", "state-failure", "--state", "DIRTY", "--event", "POLL", "--expected", "preserve draft", "--observed", "draft replaced", "--hazard-class", "competing_writer", "--suspect", "hydrateProject")
    signature = root / ".ai" / "runtime" / "state_failures" / "BUG1-r001.json"
    assert signature.is_file() and json.loads(signature.read_text(encoding="utf-8"))["event"] == "POLL"
    run(root, "debug", "evidence-infra-failure", "--method", "playwright", "--note", "browser boot failed")
    second_failure = run(root, "debug", "evidence-infra-failure", "--method", "playwright", "--note", "session failed")
    assert "STOP_LOSS" in second_failure.stdout
    assert "change acceptance method" in run(root, "next").stdout.lower()


def main() -> None:
    assert KERNEL.is_file(), f"Installed kernel missing: {KERNEL}"
    test_redaction()
    with tempfile.TemporaryDirectory(prefix="story-audio-v116-windows-") as temporary:
        base = Path(temporary)
        test_namespace_and_lock(base)
        test_state_hazard_reuse_and_debug(base)
    print("WINDOWS_V116_ACCEPTANCE: PASS")


if __name__ == "__main__":
    main()
