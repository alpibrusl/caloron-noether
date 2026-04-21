"""Security-boundary regression tests for the orchestrator.

Pins the three invariants added in the security batch 2:

1. ``GITEA_TOKEN`` env var is required — no hardcoded default (#18).
2. ``require_id`` / ``require_branch`` are called at the orchestrator's
   subprocess-facing entry points so crafted PO output can't escape the
   intended filesystem/shell surface (#19).

These live alongside ``tests/test_orchestrator_learnings.py`` which
has the sys.path shim that makes `orchestrator.orchestrator`
importable under both test-discovery styles.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Same shim as `tests/test_orchestrator_learnings.py` — orchestrator uses
# bare-name imports internally (``from agent_configurator import …``),
# so both the repo root and the orchestrator dir need to be on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORCH_DIR = _REPO_ROOT / "orchestrator"
for _p in (str(_REPO_ROOT), str(_ORCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── GITEA_TOKEN gate ──────────────────────────────────────────────────────────


def test_orchestrator_import_requires_gitea_token(monkeypatch):
    """Importing orchestrator without ``GITEA_TOKEN`` set raises a clear
    RuntimeError at module-load time — no hardcoded-default fallback.

    Closes issue #18.
    """
    monkeypatch.delenv("GITEA_TOKEN", raising=False)

    # Drop cached module so the re-import actually re-runs top-level.
    for key in list(sys.modules.keys()):
        if key.startswith("orchestrator"):
            del sys.modules[key]

    with pytest.raises(RuntimeError, match="GITEA_TOKEN"):
        import orchestrator.orchestrator  # noqa: F401 — side-effecting import


def test_orchestrator_import_succeeds_with_gitea_token(monkeypatch):
    """Smoke: the gate allows normal imports when the env var is set."""
    monkeypatch.setenv("GITEA_TOKEN", "fake-token-for-import-smoke")

    for key in list(sys.modules.keys()):
        if key.startswith("orchestrator"):
            del sys.modules[key]

    import orchestrator.orchestrator as orch_mod

    importlib.reload(orch_mod)
    assert orch_mod.GITEA_TOKEN == "fake-token-for-import-smoke"


def test_orchestrator_import_rejects_empty_gitea_token(monkeypatch):
    """Empty string must be treated the same as unset. ``os.environ.get``
    with a fallback would have returned ``""``; the gate normalises."""
    monkeypatch.setenv("GITEA_TOKEN", "   ")  # whitespace-only → empty after strip

    for key in list(sys.modules.keys()):
        if key.startswith("orchestrator"):
            del sys.modules[key]

    with pytest.raises(RuntimeError, match="GITEA_TOKEN"):
        import orchestrator.orchestrator  # noqa: F401


# ── Subprocess-boundary validation ────────────────────────────────────────────


@pytest.fixture
def orch(monkeypatch):
    """Freshly-imported orchestrator module with a fake token."""
    monkeypatch.setenv("GITEA_TOKEN", "fake-token")
    for key in list(sys.modules.keys()):
        if key.startswith("orchestrator"):
            del sys.modules[key]
    import orchestrator.orchestrator as orch_mod

    importlib.reload(orch_mod)
    return orch_mod


def test_run_agent_with_supervision_rejects_invalid_task_id(orch):
    """Crafted task_id (shell metacharacters, unicode, path traversal)
    must be rejected at the entry to ``run_agent_with_supervision``
    before it can reach subprocess.run, gitea(), or the issue-body
    interpolation. Closes the orchestrator side of #19."""
    from orchestrator.orchestrator import SupervisorState, run_agent_with_supervision

    for bad_id in [
        "task;rm -rf /",  # shell metacharacter
        "task$(whoami)",  # command substitution
        "../../../etc",  # path traversal
        "task with space",  # whitespace
        "Task-001",  # uppercase (strict matches shell validator)
        "",  # empty
        "t" * 65,  # overlong
        "\u202etask",  # right-to-left override
    ]:
        with pytest.raises(ValueError, match="invalid task_id"):
            run_agent_with_supervision(
                sandbox="/tmp/sandbox",
                project="/tmp/project",
                prompt="hi",
                task_id=bad_id,
                issue_number=1,
                supervisor=SupervisorState(),
                framework="claude-code",
            )


def test_git_merge_branch_rejects_invalid_branch(orch):
    """Crafted branch flows into ``docker exec ... sh -c "<script>"`` —
    any shell metacharacter here is direct injection. Must be rejected
    before the script is constructed."""
    from orchestrator.orchestrator import git_merge_branch

    for bad_branch in [
        "feat;rm -rf /",
        "branch$(id)",
        "branch\nmalicious",
        "Main",  # uppercase — strict enough to catch case-folding filesystems
        "",
        "x" * 129,  # overlong
    ]:
        with pytest.raises(ValueError, match="invalid branch"):
            git_merge_branch(bad_branch, "harmless message")


def test_git_merge_branch_shell_escapes_message(orch, monkeypatch):
    """Messages are arbitrary human text (PR titles) — they legitimately
    contain single quotes, dollar signs, backticks, etc. Those must be
    shell-escaped before interpolation into ``git merge -m '...'``."""
    from orchestrator.orchestrator import git_merge_branch

    # Capture the constructed shell script.
    captured_argv: list[list[str]] = []

    def fake_run(argv, **kwargs):
        captured_argv.append(list(argv))

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(orch.subprocess, "run", fake_run)

    # Nasty message with every shell-injection character.
    naughty = "title with 'quotes' and $(rm -rf /) and `whoami` and \"double\""
    git_merge_branch("feat/safe", naughty)

    # Recover the shell script that would have been exec'd.
    assert len(captured_argv) == 1
    script = captured_argv[0][-1]

    # The raw injection characters must NOT appear unquoted. shlex.quote
    # wraps in single quotes and escapes embedded single quotes via
    # `'"'"'`, so the nasty string survives but as a literal argument.
    assert "rm -rf /" not in script.split("git merge")[1].split("2>/dev/null")[0] or (
        "'" in script
    ), "naughty message must be shell-quoted, not raw-interpolated"
    # Double-sanity: shlex.quote always wraps in single quotes when input
    # contains anything non-trivial.
    assert "title with" in script  # the content is there
    # And the `$(rm -rf /)` substitution — when properly quoted — appears
    # as a literal part of the quoted string, not as a shell command.
    import shlex

    expected_quoted = shlex.quote(naughty)
    assert expected_quoted in script


def test_upload_file_rejects_invalid_branch(orch):
    """``upload_file`` uses branch in a URL ref param — validate at entry."""
    from orchestrator.orchestrator import upload_file

    with pytest.raises(ValueError, match="invalid branch"):
        upload_file("feat with space", "src/foo.py", "content", "msg")


def test_upload_file_rejects_invalid_filepath(orch):
    """Filepath is validated against the same permissive branch pattern
    (allows ``/`` and ``.`` but blocks shell metacharacters and
    traversal-unsafe chars)."""
    from orchestrator.orchestrator import upload_file

    with pytest.raises(ValueError, match="invalid filepath"):
        upload_file("feat/safe", "path with space/file.py", "x", "msg")


def test_upload_file_rejects_shell_metacharacter_in_filepath(orch):
    from orchestrator.orchestrator import upload_file

    for bad in ["foo;bar.py", "foo$bar.py", "foo`cmd`.py", "foo(bar).py"]:
        with pytest.raises(ValueError, match="invalid filepath"):
            upload_file("feat/safe", bad, "x", "msg")
