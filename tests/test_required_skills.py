"""Required-skills enforcement — fail-fast on config gaps.

Previously the agentspec bridge tracked ``missing_tools`` advisorily
but never blocked; users hit "the agent didn't use X" failures where
the real cause was that X just wasn't in the environment. v0.3.3
makes it an explicit, checkable contract: a PO-declared
``required_skills`` list on a task must be a subset of the skills the
resolver actually matched, or the task is blocked before it runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORCH_DIR = _REPO_ROOT / "orchestrator"
for _p in (str(_REPO_ROOT), str(_ORCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def orchestrator_module(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("WORK", str(tmp_path))
    import importlib

    import orchestrator.orchestrator as orch_mod

    importlib.reload(orch_mod)
    return orch_mod


# ── _resolved_skills_for ────────────────────────────────────────────────────


def test_resolved_skills_picks_up_hr_agent_skills(orchestrator_module):
    task = {"id": "t1", "skills": ["python-development"]}
    out = orchestrator_module._resolved_skills_for(task)
    assert out == {"python-development"}


def test_resolved_skills_unions_all_sources(orchestrator_module):
    task = {
        "id": "t1",
        "skills": ["python-development"],
        "tools_used": ["pytest"],
        "agentspec": {"tools": ["github"]},
    }
    out = orchestrator_module._resolved_skills_for(task)
    assert out == {"python-development", "pytest", "github"}


def test_resolved_skills_case_insensitive(orchestrator_module):
    task = {"id": "t1", "skills": ["Python-Development"]}
    out = orchestrator_module._resolved_skills_for(task)
    assert "python-development" in out


def test_resolved_skills_tolerates_non_list(orchestrator_module):
    """A non-list value (e.g. the bridge returned an error dict) must
    not crash the filter — just contribute nothing."""
    task = {"id": "t1", "skills": None, "agentspec": {"tools": "broken"}}
    out = orchestrator_module._resolved_skills_for(task)
    assert out == set()


# ── _enforce_required_skills ────────────────────────────────────────────────


def test_enforce_passes_tasks_without_requirements(orchestrator_module):
    """Tasks without ``required_skills`` (or with []) are always runnable."""
    tasks = [
        {"id": "a"},
        {"id": "b", "required_skills": []},
        {"id": "c", "skills": ["python-development"]},
    ]
    runnable, blocked = orchestrator_module._enforce_required_skills(tasks)
    assert [t["id"] for t in runnable] == ["a", "b", "c"]
    assert blocked == []


def test_enforce_blocks_when_required_skill_missing(orchestrator_module):
    tasks = [
        {
            "id": "needs-github",
            "skills": ["python-development"],
            "required_skills": ["github-pr-management"],
        }
    ]
    runnable, blocked = orchestrator_module._enforce_required_skills(tasks)
    assert runnable == []
    assert len(blocked) == 1
    assert blocked[0]["id"] == "needs-github"
    assert blocked[0]["missing"] == ["github-pr-management"]
    assert "python-development" in blocked[0]["resolved"]


def test_enforce_admits_when_agentspec_tool_satisfies_requirement(
    orchestrator_module,
):
    """Skills declared as required can be satisfied by any of the three
    resolution sources — skills list, tools_used, or agentspec.tools."""
    tasks = [
        {
            "id": "ok",
            "skills": ["python-development"],
            "agentspec": {"tools": ["github"]},
            "required_skills": ["github"],
        }
    ]
    runnable, blocked = orchestrator_module._enforce_required_skills(tasks)
    assert [t["id"] for t in runnable] == ["ok"]
    assert blocked == []


def test_enforce_splits_mixed_batch(orchestrator_module):
    tasks = [
        {"id": "a"},  # no requirements → runnable
        {
            "id": "b",
            "skills": ["python-development"],
            "required_skills": ["python-development"],
        },  # satisfied
        {
            "id": "c",
            "skills": ["python-development"],
            "required_skills": ["browser-automation"],
        },  # missing
    ]
    runnable, blocked = orchestrator_module._enforce_required_skills(tasks)
    assert [t["id"] for t in runnable] == ["a", "b"]
    assert [b["id"] for b in blocked] == ["c"]
    assert blocked[0]["missing"] == ["browser-automation"]


def test_enforce_reports_every_missing_skill(orchestrator_module):
    tasks = [
        {
            "id": "multi",
            "skills": ["python-development"],
            "required_skills": ["docker-management", "kubernetes-management"],
        }
    ]
    runnable, blocked = orchestrator_module._enforce_required_skills(tasks)
    assert runnable == []
    assert blocked[0]["missing"] == [
        "docker-management",
        "kubernetes-management",
    ]
