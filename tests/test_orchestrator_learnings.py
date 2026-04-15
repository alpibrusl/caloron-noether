"""Cover the sprint-chain learning loop that field reports flagged as broken.

Targets the three pitfalls that prompted v0.3.0:

1. ``build_po_context`` must surface prior-sprint blockers (widened in 0.3.0
   from last-sprint-only to last-3-sprints with force-merge highlighting).
2. Learnings must round-trip through disk — ``save_learnings`` → re-load →
   ``build_po_context`` — so the "each sprint starts from scratch" bug
   from v0.1–0.2 can't regress.
3. ``gitea_available`` must detect the silent-failure condition where the
   container is absent, so orchestrator can abort loudly instead of
   producing fake issue numbers.
4. ``run_agent_with_supervision`` must inherit the configured framework
   when callers omit it, so the reviewer/fixer use the right CLI.

These are unit-level tests of the pieces the reporters hit. An end-to-end
sprint-twice integration test (mocks every subprocess.run) is the next
step but is deferred pending the stub-framework work — see the v0.3.0
release notes for scope.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# orchestrator/orchestrator.py uses bare-name imports for its siblings
# (``from agent_configurator import …``), so we need both the repo root
# (for ``orchestrator.orchestrator`` package access) and the orchestrator
# directory itself (so the bare imports resolve).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORCH_DIR = _REPO_ROOT / "orchestrator"
for _p in (str(_REPO_ROOT), str(_ORCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def orchestrator_module(monkeypatch, tmp_path: Path):
    """Import orchestrator with WORK pointed at a fresh tmp dir per test.

    orchestrator.py freezes several paths (LEARNINGS_FILE, WORK) at
    module import time, so we set the env before importing and reload
    on each test to keep them isolated.
    """
    monkeypatch.setenv("WORK", str(tmp_path))
    monkeypatch.setenv("CALORON_FRAMEWORK", "gemini-cli")
    import importlib

    import orchestrator.orchestrator as orch_mod  # noqa: E402

    importlib.reload(orch_mod)
    return orch_mod


# ── build_po_context ─────────────────────────────────────────────────────────


def test_build_po_context_empty_on_first_sprint(orchestrator_module):
    """No prior sprints → empty context (falsy — signals first run)."""
    out = orchestrator_module.build_po_context({"sprints": [], "improvements": []})
    assert out == ""


def test_build_po_context_surfaces_last_sprint_kpis(orchestrator_module):
    learnings = {
        "sprints": [
            {
                "sprint_id": "sprint-1",
                "total": 4,
                "completed": 3,
                "avg_clarity": 6.5,
                "supervisor_events": 1,
                "blockers": ["CLAUDE.md scope blocked writing pyproject.toml"],
            }
        ],
        "improvements": [],
    }
    ctx = orchestrator_module.build_po_context(learnings)
    assert "Recent sprints" in ctx
    assert "sprint-1" in ctx
    assert "3/4 tasks" in ctx
    # The blocker must survive so PO sprint-2 prompt can address it.
    assert "CLAUDE.md scope" in ctx


def test_build_po_context_carries_three_sprints(orchestrator_module):
    learnings = {
        "sprints": [
            {"sprint_id": f"sprint-{i}", "total": 3, "completed": i, "avg_clarity": 5.0,
             "supervisor_events": 0, "blockers": []}
            for i in range(1, 6)  # five sprints
        ],
        "improvements": [],
    }
    ctx = orchestrator_module.build_po_context(learnings)
    # Should show the last 3, not the first 3.
    assert "sprint-3" in ctx
    assert "sprint-4" in ctx
    assert "sprint-5" in ctx
    assert "sprint-1" not in ctx


def test_build_po_context_escalates_force_merged(orchestrator_module):
    """Force-merged blockers must be surfaced as their own section so the
    next sprint's PO can treat them as tech debt, not just drop them into
    the generic blockers list."""
    learnings = {
        "sprints": [
            {
                "sprint_id": "sprint-1",
                "total": 2,
                "completed": 2,
                "avg_clarity": 7.0,
                "supervisor_events": 0,
                "blockers": [
                    "some mundane blocker",
                    "⚠️ FORCE-MERGED after 3 review cycles — unresolved: missing test for concurrent writes",
                ],
            }
        ],
        "improvements": [],
    }
    ctx = orchestrator_module.build_po_context(learnings)
    # Force-merge gets the escalated section with its own heading.
    assert "Unresolved feedback from force-merged" in ctx
    assert "missing test for concurrent writes" in ctx
    # Mundane blocker lands in the regular section — not escalated.
    assert "some mundane blocker" in ctx


def test_build_po_context_carries_improvements(orchestrator_module):
    learnings = {
        "sprints": [{"sprint_id": "sprint-1", "total": 1, "completed": 1,
                     "avg_clarity": 5, "supervisor_events": 0, "blockers": []}],
        "improvements": ["Lower ambiguity in task titles", "Add type hints earlier"],
    }
    ctx = orchestrator_module.build_po_context(learnings)
    assert "Pending improvements" in ctx
    assert "Lower ambiguity in task titles" in ctx


# ── Learnings disk round-trip ────────────────────────────────────────────────


def test_load_learnings_empty_when_file_missing(orchestrator_module):
    """First-ever sprint: no file on disk → empty shape, no crash."""
    # Tmp WORK dir is fresh; no learnings.json yet.
    loaded = orchestrator_module.load_learnings()
    assert loaded == {"sprints": [], "improvements": [], "po_context": ""}


def test_save_then_load_roundtrip(orchestrator_module, tmp_path: Path):
    """Exactly the path the user reported broken: save in sprint 1,
    re-load at sprint 2 start, feed to build_po_context."""
    sprint1 = {
        "sprints": [
            {
                "sprint_id": "sprint-1",
                "total": 3,
                "completed": 2,
                "failed": 1,
                "avg_clarity": 6.0,
                "supervisor_events": 0,
                "blockers": ["CLAUDE.md blocked writing pyproject.toml"],
            }
        ],
        "improvements": ["Accept broader scope"],
    }
    orchestrator_module.save_learnings(sprint1)

    # File actually lands where LEARNINGS_FILE points — i.e. under WORK.
    assert Path(orchestrator_module.LEARNINGS_FILE).exists()
    assert Path(orchestrator_module.LEARNINGS_FILE).parent == tmp_path

    reloaded = orchestrator_module.load_learnings()
    assert reloaded["sprints"][0]["sprint_id"] == "sprint-1"

    # The whole reason users care about the round-trip: does the PO
    # prompt on sprint 2 actually see sprint 1's blockers?
    ctx = orchestrator_module.build_po_context(reloaded)
    assert "CLAUDE.md blocked writing pyproject.toml" in ctx
    assert "Accept broader scope" in ctx


# ── Gitea preflight ──────────────────────────────────────────────────────────


def test_gitea_available_missing_container(monkeypatch, orchestrator_module):
    """Simulates the `caloron sprint` → docker ps empty scenario."""

    def _fake_run(cmd, *a, **kw):
        if cmd[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(orchestrator_module.subprocess, "run", _fake_run)
    ok, detail = orchestrator_module.gitea_available()
    assert ok is False
    assert "no running container" in detail


def test_gitea_available_container_present(monkeypatch, orchestrator_module):
    def _fake_run(cmd, *a, **kw):
        if cmd[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="gitea\n", stderr="")
        if cmd[:3] == ["docker", "exec", "gitea"]:
            return subprocess.CompletedProcess(cmd, 0, stdout='{"version":"1.22.1"}', stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(orchestrator_module.subprocess, "run", _fake_run)
    ok, detail = orchestrator_module.gitea_available()
    assert ok is True
    assert "1.22.1" in detail


def test_gitea_available_docker_missing(monkeypatch, orchestrator_module):
    """Environments without docker installed at all — honest detail."""

    def _fake_run(cmd, *a, **kw):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(orchestrator_module.subprocess, "run", _fake_run)
    ok, detail = orchestrator_module.gitea_available()
    assert ok is False
    assert "docker" in detail.lower()


# ── Reviewer/fixer framework propagation ─────────────────────────────────────


def test_run_agent_with_supervision_defaults_to_configured_framework(
    monkeypatch, orchestrator_module
):
    """Reviewer used to hardcode claude-code even when CALORON_FRAMEWORK
    was something else. Make sure that regression stays fixed."""
    captured: dict = {}

    def _fake_build_agent_command(framework, prompt):
        captured["framework"] = framework
        return [framework, "-p", prompt]

    def _fake_run(cmd, *a, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="APPROVED", stderr="")

    monkeypatch.setattr(orchestrator_module, "build_agent_command", _fake_build_agent_command)
    monkeypatch.setattr(orchestrator_module.subprocess, "run", _fake_run)

    supervisor = orchestrator_module.SupervisorState()
    out, ok = orchestrator_module.run_agent_with_supervision(
        sandbox="/bin/true",
        project="/tmp",
        prompt="review this",
        task_id="t1",
        issue_number=1,
        supervisor=supervisor,
        # framework not passed — must fall back to CALORON_FRAMEWORK from the env,
        # which the fixture set to "gemini-cli".
    )
    assert ok is True
    assert captured["framework"] == "gemini-cli"


def test_run_agent_with_supervision_honours_explicit_framework(
    monkeypatch, orchestrator_module
):
    """Callers can still override per-task."""
    captured: dict = {}

    def _fake_build_agent_command(framework, prompt):
        captured["framework"] = framework
        return [framework, "-p", prompt]

    def _fake_run(cmd, *a, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="done", stderr="")

    monkeypatch.setattr(orchestrator_module, "build_agent_command", _fake_build_agent_command)
    monkeypatch.setattr(orchestrator_module.subprocess, "run", _fake_run)

    supervisor = orchestrator_module.SupervisorState()
    out, ok = orchestrator_module.run_agent_with_supervision(
        sandbox="/bin/true",
        project="/tmp",
        prompt="do the thing",
        task_id="t2",
        issue_number=2,
        supervisor=supervisor,
        framework="codex-cli",
    )
    assert captured["framework"] == "codex-cli"


# ── Path filter ──────────────────────────────────────────────────────────────


def test_is_caloron_managed_protects_generated_files(orchestrator_module):
    assert orchestrator_module._is_caloron_managed("CLAUDE.md") is True
    assert orchestrator_module._is_caloron_managed(".mcp.json") is True
    assert orchestrator_module._is_caloron_managed(".caloron/state.json") is True


def test_is_caloron_managed_allows_project_files(orchestrator_module):
    # Previously filtered out by the src/+tests/ whitelist.
    assert orchestrator_module._is_caloron_managed("pyproject.toml") is False
    assert orchestrator_module._is_caloron_managed("Dockerfile") is False
    assert orchestrator_module._is_caloron_managed("config/settings.yaml") is False
    assert orchestrator_module._is_caloron_managed("migrations/001_init.sql") is False
    # And the happy path still works.
    assert orchestrator_module._is_caloron_managed("src/api.py") is False
    assert orchestrator_module._is_caloron_managed("tests/test_api.py") is False
