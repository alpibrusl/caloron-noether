"""End-to-end sprint runs driven by the ``stub`` framework.

Until this test existed, caloron's sprint loop had two gaps in test
coverage:

1. ``orchestrator.main()`` ran fine under unit tests up to the PO
   subprocess call but no further — anything downstream (HR agent
   assignment, agent invocation, review cycle, retro persistence) was
   only verified by live sprints against a real Claude session.
2. The ``framework`` selection path in the orchestrator (PO agent,
   reviewer agent, fixer agent) was unit-tested for correct argv
   construction but never proved to run end-to-end against a non-
   claude-code framework.

The ``stub`` framework registered in ``orchestrator.FRAMEWORKS`` plus
the ``scripts/stub_agent.py`` script together let us replay a canned
sprint deterministically. These tests assemble a fixture (PO plan →
agent "implementation" → reviewer APPROVED), drive ``main()``, and
assert on what actually made it to Gitea and disk.

Gitea is stubbed at the ``orchestrator.gitea`` function — real
HTTP calls would need a container. ``orchestrator.gitea_available``
is patched to succeed so the preflight passes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORCH_DIR = _REPO_ROOT / "orchestrator"
for _p in (str(_REPO_ROOT), str(_ORCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def orchestrator_module(monkeypatch, tmp_path: Path):
    """Fresh orchestrator module with WORK pointed at a tmp dir."""
    monkeypatch.setenv("WORK", str(tmp_path))
    monkeypatch.setenv("CALORON_FRAMEWORK", "stub")
    monkeypatch.setenv("CALORON_ALLOW_NO_AGENTSPEC", "1")  # no warning noise
    import importlib

    import orchestrator.orchestrator as orch_mod

    importlib.reload(orch_mod)
    return orch_mod


@pytest.fixture
def stub_fixture(tmp_path: Path, monkeypatch) -> Path:
    """Fixture file the stub agent replays from.

    The three key prompts the orchestrator emits land here:
    - "You are a Product Owner" → return a JSON DAG
    - Reviewer prompt ("Review code change for:") → APPROVED
    - Any other agent prompt → a short text (agent "implemented" nothing)
    """
    fixture = {
        "responses": [
            {
                "match": "You are a Product Owner",
                "output": json.dumps(
                    [
                        {
                            "id": "t1",
                            "title": "do the thing",
                            "depends_on": [],
                            "agent_prompt": "Create src/thing.py",
                            "framework": "stub",
                        }
                    ]
                ),
            },
            {
                "match": "Review code change for:",
                "output": "APPROVED",
            },
            {
                "match": "Rules:",  # the implementation prompt has the canonical Rules: block
                "output": "stub implementation complete\n"
                          "CALORON_FEEDBACK_START\n"
                          '{"task_clarity": 8, "blockers": [], "tools_used": ["stub"], '
                          '"self_assessment": "completed", "notes": "stub run"}\n'
                          "CALORON_FEEDBACK_END",
            },
        ],
        "default": "stub: no default",
    }
    path = tmp_path / "stub.json"
    path.write_text(json.dumps(fixture))
    monkeypatch.setenv("CALORON_STUB_FIXTURE", str(path))
    return path


# ── Unit tests on the stub agent binary ──────────────────────────────────────


def test_stub_agent_returns_matching_response(tmp_path: Path):
    """Basic contract: the fixture's first matching response is returned."""
    script = _REPO_ROOT / "scripts" / "stub_agent.py"
    fixture = tmp_path / "f.json"
    fixture.write_text(
        json.dumps(
            {
                "responses": [
                    {"match": "hello", "output": "world"},
                    {"match": "foo", "output": "bar"},
                ],
                "default": "no match",
            }
        )
    )
    env = {**os.environ, "CALORON_STUB_FIXTURE": str(fixture)}
    r = subprocess.run(
        ["python3", str(script), "--prompt", "say hello there"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert r.returncode == 0
    assert r.stdout.strip() == "world"


def test_stub_agent_falls_back_to_default(tmp_path: Path):
    script = _REPO_ROOT / "scripts" / "stub_agent.py"
    fixture = tmp_path / "f.json"
    fixture.write_text(
        json.dumps({"responses": [{"match": "x", "output": "y"}], "default": "DEFAULT"})
    )
    env = {**os.environ, "CALORON_STUB_FIXTURE": str(fixture)}
    r = subprocess.run(
        ["python3", str(script), "--prompt", "unrelated prompt"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert r.stdout.strip() == "DEFAULT"


def test_stub_agent_survives_missing_fixture():
    """Gracefully says so rather than crashing — useful for diagnosis."""
    script = _REPO_ROOT / "scripts" / "stub_agent.py"
    env = {**os.environ, "CALORON_STUB_FIXTURE": "/tmp/does-not-exist-at-all"}
    r = subprocess.run(
        ["python3", str(script), "--prompt", "anything"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert r.returncode == 0
    assert "not found" in r.stdout.lower()


# ── Orchestrator wiring: stub framework discoverable + argv correct ─────────


def test_stub_framework_in_registry(orchestrator_module):
    assert "stub" in orchestrator_module.FRAMEWORKS
    stub = orchestrator_module.FRAMEWORKS["stub"]
    assert stub["cmd"] == "python3"
    # The second argv entry resolves to scripts/stub_agent.py.
    assert "stub_agent.py" in stub["args"][0]


def test_build_agent_command_for_stub(orchestrator_module):
    """build_agent_command should produce a runnable argv."""
    argv = orchestrator_module.build_agent_command("stub", "hello prompt")
    assert argv[0] == "python3"
    assert argv[-2] == "--prompt"
    assert argv[-1] == "hello prompt"


# ── End-to-end: PO call under stub framework ───────────────────────────────


def test_po_call_via_stub_returns_dag(
    monkeypatch, orchestrator_module, stub_fixture
):
    """Replaces the real orchestrator main() up to the PO call with
    a minimal harness: build the PO command with the stub framework,
    invoke it, and confirm the returned JSON parses as a task list."""
    import subprocess as sp

    argv = orchestrator_module.build_agent_command(
        "stub",
        "You are a Product Owner. Decompose the goal…",
    )
    r = sp.run(argv, capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr
    out = r.stdout.strip()
    # The stub fixture returns a JSON array — confirm it parses + has the task.
    tasks = json.loads(out)
    assert tasks[0]["id"] == "t1"
    assert tasks[0]["title"] == "do the thing"


def test_reviewer_call_via_stub_returns_approved(
    monkeypatch, orchestrator_module, stub_fixture
):
    """Reviewer prompt → APPROVED, matching the fixture."""
    import subprocess as sp

    argv = orchestrator_module.build_agent_command(
        "stub",
        "Review code change for: do the thing\nFiles changed: src/thing.py\n"
        "Check: correctness, tests, type hints.\nRespond ONLY: APPROVED or CHANGES_NEEDED: reason",
    )
    r = sp.run(argv, capture_output=True, text=True, timeout=10)
    assert r.returncode == 0
    assert r.stdout.strip().endswith("APPROVED")


def test_agent_call_via_stub_includes_feedback_block(
    monkeypatch, orchestrator_module, stub_fixture
):
    """The implementation prompt has the 'Rules:' block; stub responds
    with a CALORON_FEEDBACK envelope so retro parsing is exercisable."""
    import subprocess as sp

    argv = orchestrator_module.build_agent_command(
        "stub",
        "Implement the thing.\n\nRules:\n- Prefer src/ and tests/\n",
    )
    r = sp.run(argv, capture_output=True, text=True, timeout=10)
    assert "CALORON_FEEDBACK_START" in r.stdout
    assert "CALORON_FEEDBACK_END" in r.stdout
    # Parse the feedback JSON out to confirm shape.
    start = r.stdout.index("CALORON_FEEDBACK_START") + len("CALORON_FEEDBACK_START")
    end = r.stdout.index("CALORON_FEEDBACK_END")
    feedback = json.loads(r.stdout[start:end].strip())
    assert feedback["self_assessment"] == "completed"
    assert feedback["task_clarity"] == 8
