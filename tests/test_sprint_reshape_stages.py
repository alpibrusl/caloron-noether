"""Tests for the sprint-tick boundary reshape stages.

These stages exist only to realign data between Let bindings and the
stages that consume them. They're tiny — a few lines each — so the
tests are proportionally small. The point of having tests at all is:

1. Contract stability. If someone "improves" a reshape stage in a way
   that changes its output shape, every downstream stage in
   sprint_tick_core starts mismatching at type-check time. Catching
   the shape drift here is faster than finding it via dry-run.

2. Default handling. The stages need to not crash when a nested
   record is missing or partially populated — real sprint-tick input
   may have ``agents: {}`` or ``interventions: {}`` on the first tick.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "stages" / "sprint")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import project_all_to_execute  # noqa: E402, I001
import project_health_to_intervention  # noqa: E402, I001
import project_poll_to_eval  # noqa: E402, I001


# ── project_poll_to_eval ────────────────────────────────────────────────────


def test_poll_to_eval_extracts_events_from_binding():
    out = project_poll_to_eval.execute(
        {
            "state": {"tasks": {}},
            "poll": {"events": [{"type": "issue_opened"}], "polled_at": "2026-04-15T10:00:00Z"},
            "stall_threshold_m": 20,
        }
    )
    assert out == {
        "state": {"tasks": {}},
        "events": [{"type": "issue_opened"}],
        "stall_threshold_m": 20,
    }


def test_poll_to_eval_tolerates_missing_poll_binding():
    """First-ever tick may have an empty events list. Shouldn't crash."""
    out = project_poll_to_eval.execute(
        {"state": {"tasks": {}}, "poll": {}, "stall_threshold_m": 20}
    )
    assert out["events"] == []


def test_poll_to_eval_coerces_stall_threshold_to_int():
    """Noether can pass numbers as floats; dag_evaluate uses this as an int."""
    out = project_poll_to_eval.execute(
        {"state": {}, "poll": {"events": []}, "stall_threshold_m": 20.0}
    )
    assert out["stall_threshold_m"] == 20
    assert isinstance(out["stall_threshold_m"], int)


# ── project_health_to_intervention ──────────────────────────────────────────


def test_health_to_intervention_pulls_results_and_keeps_interventions():
    out = project_health_to_intervention.execute(
        {
            "health": {"results": [{"agent_id": "a", "healthy": False}]},
            "interventions": {"a": {"count": 1}},
        }
    )
    assert out == {
        "results": [{"agent_id": "a", "healthy": False}],
        "interventions": {"a": {"count": 1}},
    }


def test_health_to_intervention_defaults_empty():
    out = project_health_to_intervention.execute({})
    assert out == {"results": [], "interventions": {}}


# ── project_all_to_execute ──────────────────────────────────────────────────


def test_all_to_execute_assembles_execute_actions_input():
    out = project_all_to_execute.execute(
        {
            "eval": {"state": {}, "actions": [{"type": "spawn_agent", "task_id": "t1"}]},
            "supervisor": {
                "actions": [{"type": "notify_agent", "task_id": "t1"}],
                "updated_interventions": {"t1": {"count": 1}},
            },
            "repo": "owner/repo",
            "token_env": "GITHUB_TOKEN",
            "shell_url": "http://localhost:7710",
            "sprint_id": "sprint-1",
        }
    )
    assert out == {
        "repo": "owner/repo",
        "token_env": "GITHUB_TOKEN",
        "shell_url": "http://localhost:7710",
        "dag_actions": [{"type": "spawn_agent", "task_id": "t1"}],
        "supervisor_actions": [{"type": "notify_agent", "task_id": "t1"}],
        "sprint_id": "sprint-1",
    }


def test_all_to_execute_defaults_missing_action_lists():
    out = project_all_to_execute.execute(
        {
            "eval": {},
            "supervisor": {},
            "repo": "r",
            "token_env": "T",
            "shell_url": "s",
            "sprint_id": "sp1",
        }
    )
    assert out["dag_actions"] == []
    assert out["supervisor_actions"] == []
