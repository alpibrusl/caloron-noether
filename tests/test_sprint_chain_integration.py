"""End-to-end: sprint 1's learnings actually reach sprint 2's PO argv.

Up until this test, the learning-loop claim was only verified at the
function boundary (``build_po_context`` returns non-empty when given
previous sprints). This test closes the remaining gap by running
``orchestrator.main()`` twice in the same WORK dir — with enough
subprocess + Gitea mocking to keep the state machine alive until the
PO is invoked — and asserting the exact argv passed to the PO
subprocess contains sprint 1's blocker text.

If this test regresses, it means some future refactor broke the
plumbing between ``save_learnings`` and the ``subprocess.run`` call
that launches claude — which is the exact bug the first field report
hit and unit tests couldn't catch.

Strategy:
- Patch ``gitea_available`` and ``subprocess.run`` at the module level.
- ``subprocess.run`` has to keep the main() flow alive through git
  init/config (returns success) and intercept only the PO call (raises
  a sentinel exception that the test catches).
- Sprint 1: seed nothing; run main(); catch the PO call; save a
  synthetic sprint-1 record via ``save_learnings`` to simulate the
  retro that would normally run after a full sprint.
- Sprint 2: re-run main() in the same WORK dir; catch the PO call;
  assert the captured argv contains sprint 1's blocker string verbatim.

Why not run main() fully to completion and inspect the real retro?
Because the full sprint needs Gitea, a real (or stub) agent, git
server, and reviewer — each an integration surface. Intercepting at
the PO boundary is the tightest possible test of the specific claim
and doesn't require standing up that infrastructure. The stub-agent
framework for full-loop integration tests is tracked separately.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORCH_DIR = _REPO_ROOT / "orchestrator"
for _p in (str(_REPO_ROOT), str(_ORCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class _POCallIntercepted(Exception):
    """Raised by the mock subprocess.run when it spots the PO call."""

    def __init__(self, argv: list[str]):
        super().__init__("PO subprocess call intercepted")
        self.argv = argv


@pytest.fixture
def orchestrator_module(monkeypatch, tmp_path: Path):
    """Import orchestrator with WORK pointed at a fresh tmp dir per test."""
    monkeypatch.setenv("WORK", str(tmp_path))
    monkeypatch.setenv("CALORON_FRAMEWORK", "claude-code")
    import importlib

    import orchestrator.orchestrator as orch_mod

    importlib.reload(orch_mod)
    return orch_mod


def _install_intercepting_subprocess(monkeypatch, orch_mod):
    """Install a subprocess.run mock that keeps main() alive until PO.

    Returns nothing — the interception raises ``_POCallIntercepted`` with
    the captured argv. Fails the test early with a clear message if any
    unexpected subprocess shape shows up, rather than silently proceeding.
    """

    def _mock_run(cmd, *args, **kwargs):
        # Normalise to a list of str for matching.
        argv = [str(x) for x in cmd]
        flat = " ".join(argv)

        # Git plumbing the orchestrator uses in its project-init block.
        if argv and argv[0] == "git":
            # git diff --cached --quiet returns 1 if there are staged
            # changes; return 0 so the `or` short-circuit skips commit.
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        # Intercept the PO call — the one we actually care about.
        if "You are a Product Owner" in flat:
            raise _POCallIntercepted(argv)

        # Anything else would be unexpected at this stage of main().
        # Fail loudly so the test surfaces the real cause rather than
        # looking like a pass.
        raise AssertionError(f"unexpected subprocess.run in main(): {cmd!r}")

    # Gitea preflight: say yes so main() continues past it.
    monkeypatch.setattr(orch_mod, "gitea_available", lambda: (True, "1.22.1"))
    monkeypatch.setattr(orch_mod.subprocess, "run", _mock_run)


def _drive_main_and_capture_po_argv(
    monkeypatch, orch_mod, goal: str
) -> list[str]:
    """Invoke main() and return the argv captured at the PO subprocess call."""
    _install_intercepting_subprocess(monkeypatch, orch_mod)
    monkeypatch.setattr(orch_mod.sys, "argv", ["orchestrator", goal])

    with pytest.raises(_POCallIntercepted) as excinfo:
        orch_mod.main()
    return excinfo.value.argv


# ── Tests ────────────────────────────────────────────────────────────────────


def test_sprint_1_po_argv_has_no_prior_learnings(
    monkeypatch, orchestrator_module
):
    """Baseline: first sprint in a fresh WORK dir gets an empty context
    section in its PO prompt — no hallucinated 'previous sprints' text."""
    argv = _drive_main_and_capture_po_argv(
        monkeypatch, orchestrator_module, "Build the first thing"
    )
    po_prompt = " ".join(argv)
    assert "You are a Product Owner" in po_prompt
    assert "Build the first thing" in po_prompt
    # Crucially: no previous-sprint headers when there were none.
    assert "Learnings from Previous Sprints" not in po_prompt
    assert "Recurring themes" not in po_prompt


def test_sprint_2_po_argv_carries_sprint_1_blockers(
    monkeypatch, orchestrator_module
):
    """The full integration claim: save sprint 1 → launch sprint 2 →
    the claude subprocess's argv literally contains sprint 1's blocker
    text. This is the path the first field report proved was broken.
    """
    # Simulate sprint 1's retro having written to disk.
    sprint1 = {
        "sprints": [
            {
                "sprint_id": "sprint-1",
                "total": 3,
                "completed": 2,
                "failed": 1,
                "avg_clarity": 6.0,
                "supervisor_events": 0,
                "blockers": [
                    "CLAUDE.md scope blocked writing pyproject.toml",
                    "⚠️ FORCE-MERGED after 3 review cycles — unresolved: missing test for concurrency",
                ],
            }
        ],
        "improvements": ["Loosen default scope to allow project files"],
    }
    orchestrator_module.save_learnings(sprint1)

    # Launch what the user would run as sprint 2.
    argv = _drive_main_and_capture_po_argv(
        monkeypatch, orchestrator_module, "Add rate limiting to the API"
    )
    po_prompt = " ".join(argv)

    # The goal itself propagated.
    assert "Add rate limiting to the API" in po_prompt

    # Every field report's hallmark: blocker text survives the chain.
    assert "CLAUDE.md scope blocked writing pyproject.toml" in po_prompt
    assert "Loosen default scope to allow project files" in po_prompt

    # Force-merge escalation surfaces in its own section, not just the
    # regular blockers tail — build_po_context calls this out explicitly.
    assert "Unresolved feedback from force-merged" in po_prompt
    assert "missing test for concurrency" in po_prompt


def test_po_argv_carries_organisation_conventions(
    monkeypatch, orchestrator_module
):
    """Conventions from CALORON_CONVENTIONS env must appear verbatim in
    the PO prompt — this is the v0.3.2 plumbing claim for org-wide
    house style injection. If this breaks, the caloron sprint CLI
    can populate the env var without agents ever seeing it.
    """
    convention_block = (
        "## Organisation Conventions\n"
        "(Organisation: TestCo)\n\n"
        "### Package & module naming\n"
        "- Package names use **kebab-case**.\n"
        "- All package names must start with `testco-`.\n"
    )
    monkeypatch.setenv("CALORON_CONVENTIONS", convention_block)
    # Reload so the module-level CONVENTIONS picks it up.
    import importlib

    importlib.reload(orchestrator_module)

    argv = _drive_main_and_capture_po_argv(
        monkeypatch, orchestrator_module, "Build the thing"
    )
    po_prompt = " ".join(argv)
    assert "Organisation Conventions" in po_prompt
    assert "TestCo" in po_prompt
    assert "kebab-case" in po_prompt
    assert "testco-" in po_prompt


def test_po_argv_omits_conventions_header_when_env_is_empty(
    monkeypatch, orchestrator_module
):
    """No conventions → no empty header in the prompt (avoids cache
    invalidation and prompt bloat when a user hasn't configured anything)."""
    monkeypatch.delenv("CALORON_CONVENTIONS", raising=False)
    import importlib

    importlib.reload(orchestrator_module)

    argv = _drive_main_and_capture_po_argv(
        monkeypatch, orchestrator_module, "Build the thing"
    )
    po_prompt = " ".join(argv)
    assert "Organisation Conventions" not in po_prompt


def test_sprint_6_po_argv_is_compressed_not_verbatim(
    monkeypatch, orchestrator_module
):
    """Context-compression (v0.3.1) claim: at sprint 6 the PO prompt
    should NOT contain every old sprint's full blocker list — otherwise
    we'd hit the field-reported timeout at sprint 5-6 again."""
    # Seed 5 prior sprints, each with a distinctive blocker.
    sprints = []
    for i in range(1, 6):
        sprints.append(
            {
                "sprint_id": f"sprint-{i}",
                "total": 2,
                "completed": 2,
                "failed": 0,
                "avg_clarity": 7.0,
                "supervisor_events": 0,
                "blockers": [f"historical-blocker-{i}"],
            }
        )
    orchestrator_module.save_learnings(
        {"sprints": sprints, "improvements": []}
    )

    argv = _drive_main_and_capture_po_argv(
        monkeypatch, orchestrator_module, "Sprint 6 goal"
    )
    po_prompt = " ".join(argv)

    # Older sprints (1-3) got compressed into the aggregate; their
    # individual blocker strings do NOT appear verbatim.
    for i in (1, 2, 3):
        assert f"historical-blocker-{i}" not in po_prompt, (
            f"sprint-{i}'s blocker leaked verbatim — compression regressed"
        )
    # But the two most recent (4, 5) are in the detailed window.
    assert "sprint-4" in po_prompt
    assert "sprint-5" in po_prompt
    # And the aggregate-summary marker is present.
    assert "earlier sprint(s) compressed" in po_prompt
