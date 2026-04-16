"""Tests for sprint_tick_stateful's KV load/save stages.

These stages manage persistence between ticks. Regressions here
correspond to real user pain: state silently lost, first-tick behaviour
subtly wrong, concurrent sprints trampling each other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "stages" / "sprint")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_tick_output  # noqa: E402, I001
import load_tick_state  # noqa: E402, I001
import save_tick_state  # noqa: E402, I001


@pytest.fixture
def kv_dir(tmp_path: Path, monkeypatch) -> Path:
    """Point the stages at an isolated KV dir per test."""
    d = tmp_path / "kv"
    monkeypatch.setenv("CALORON_KV_DIR", str(d))
    return d


# ── load_tick_state ─────────────────────────────────────────────────────────


def test_load_first_tick_returns_empty_state_defaults(kv_dir: Path):
    """Cold start: no persisted file → empty state, empty agents, empty since."""
    out = load_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "repo": "owner/repo",
            "stall_threshold_m": 20,
            "token_env": "GITHUB_TOKEN",
            "shell_url": "http://localhost:7710",
        }
    )
    assert out["sprint_id"] == "sprint-1"
    assert out["state"] == {"tasks": {}}
    assert out["agents"] == {}
    assert out["interventions"] == {}
    assert out["since"] == ""


def test_load_passes_host_through_unchanged(kv_dir: Path):
    """v0.4.2: ``host`` threads from scheduler input → load_tick_state →
    sprint_tick_core's downstream github stages without further glue."""
    out = load_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "repo": "o/r",
            "stall_threshold_m": 20,
            "token_env": "GITEA_TOKEN",
            "shell_url": "http://localhost:7710",
            "host": "http://gitea.local:3000/api/v1",
        }
    )
    assert out["host"] == "http://gitea.local:3000/api/v1"


def test_load_defaults_host_to_empty_string(kv_dir: Path):
    """No host given → empty string, which github_* stages interpret as
    'use api.github.com'. Backwards-compatible with pre-0.4.2 callers."""
    out = load_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "repo": "o/r",
            "stall_threshold_m": 20,
            "token_env": "GITHUB_TOKEN",
            "shell_url": "",
        }
    )
    assert out["host"] == ""


def test_load_reads_persisted_state(kv_dir: Path):
    kv_dir.mkdir(parents=True)
    (kv_dir / "sprint-1.json").write_text(
        json.dumps(
            {
                "state": {"tasks": {"t1": {"status": "Done"}}},
                "interventions": {"a1": {"count": 1}},
                "since": "2026-04-15T10:00:00Z",
            }
        )
    )
    out = load_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "repo": "o/r",
            "stall_threshold_m": 20,
            "token_env": "GITHUB_TOKEN",
            "shell_url": "http://localhost:7710",
        }
    )
    assert out["state"] == {"tasks": {"t1": {"status": "Done"}}}
    assert out["interventions"] == {"a1": {"count": 1}}
    assert out["since"] == "2026-04-15T10:00:00Z"


def test_load_tolerates_malformed_state_file(kv_dir: Path):
    """A corrupt JSON file must not crash the tick — fall back to defaults."""
    kv_dir.mkdir(parents=True)
    (kv_dir / "sprint-1.json").write_text("not: valid: json: {")
    out = load_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "repo": "o/r",
            "stall_threshold_m": 20,
            "token_env": "X",
            "shell_url": "",
        }
    )
    assert out["state"] == {"tasks": {}}


def test_load_caller_overrides_persisted_values(kv_dir: Path):
    """Outer input wins — lets callers inject state for testing/migration."""
    kv_dir.mkdir(parents=True)
    (kv_dir / "sprint-1.json").write_text(
        json.dumps({"state": {"tasks": {"persisted": 1}}})
    )
    out = load_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "repo": "o/r",
            "stall_threshold_m": 20,
            "token_env": "X",
            "shell_url": "",
            "state": {"tasks": {"override": 1}},
        }
    )
    assert out["state"] == {"tasks": {"override": 1}}


def test_load_rejects_empty_sprint_id(kv_dir: Path):
    with pytest.raises(ValueError, match="sprint_id"):
        load_tick_state.execute(
            {
                "sprint_id": "",
                "repo": "o/r",
                "stall_threshold_m": 20,
                "token_env": "X",
                "shell_url": "",
            }
        )


# ── save_tick_state ─────────────────────────────────────────────────────────


def test_save_writes_forward_carry_fields(kv_dir: Path):
    out = save_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "tick_result": {
                "actions_taken": ["spawned a1"],
                "errors": [],
                "state": {"tasks": {"t1": {"status": "InProgress"}}},
                "polled_at": "2026-04-15T10:05:00Z",
                "interventions": {"a1": {"count": 1}},
            },
        }
    )
    assert out["actions_taken"] == ["spawned a1"]
    assert out["errors"] == []
    persisted = json.loads((kv_dir / "sprint-1.json").read_text())
    assert persisted["state"] == {"tasks": {"t1": {"status": "InProgress"}}}
    assert persisted["since"] == "2026-04-15T10:05:00Z"
    assert persisted["interventions"] == {"a1": {"count": 1}}


def test_save_creates_kv_dir_if_missing(kv_dir: Path):
    """First tick — directory doesn't exist yet."""
    assert not kv_dir.exists()
    save_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "tick_result": {
                "actions_taken": [],
                "errors": [],
                "state": {},
                "polled_at": "",
                "interventions": {},
            },
        }
    )
    assert kv_dir.is_dir()


def test_save_is_atomic(kv_dir: Path):
    """tmp file gets renamed, not left behind — the .tmp file should
    NOT still exist after execute returns."""
    save_tick_state.execute(
        {
            "sprint_id": "sprint-1",
            "tick_result": {
                "actions_taken": [],
                "errors": [],
                "state": {},
                "polled_at": "",
                "interventions": {},
            },
        }
    )
    leftover_tmps = list(kv_dir.glob("*.tmp"))
    assert leftover_tmps == []


def test_save_persists_per_sprint_id(kv_dir: Path):
    """Concurrent sprints don't trample — each writes its own file."""
    for sid, marker in [("s1", "alpha"), ("s2", "beta")]:
        save_tick_state.execute(
            {
                "sprint_id": sid,
                "tick_result": {
                    "actions_taken": [],
                    "errors": [],
                    "state": {"marker": marker},
                    "polled_at": "",
                    "interventions": {},
                },
            }
        )
    a = json.loads((kv_dir / "s1.json").read_text())
    b = json.loads((kv_dir / "s2.json").read_text())
    assert a["state"]["marker"] == "alpha"
    assert b["state"]["marker"] == "beta"


# ── build_tick_output ───────────────────────────────────────────────────────


def test_build_tick_output_assembles_full_result():
    out = build_tick_output.execute(
        {
            "execute_result": {"actions_taken": ["spawn:t1"], "errors": []},
            "eval": {"state": {"tasks": {}}, "actions": []},
            "poll": {"events": [], "polled_at": "2026-04-15T10:00:00Z"},
            "supervisor": {"actions": [], "updated_interventions": {"a1": {"count": 2}}},
        }
    )
    assert out == {
        "actions_taken": ["spawn:t1"],
        "errors": [],
        "state": {"tasks": {}},
        "polled_at": "2026-04-15T10:00:00Z",
        "interventions": {"a1": {"count": 2}},
    }


def test_build_tick_output_defaults_missing_bindings():
    out = build_tick_output.execute({})
    assert out == {
        "actions_taken": [],
        "errors": [],
        "state": {},
        "polled_at": "",
        "interventions": {},
    }


# ── Round-trip: save → load ─────────────────────────────────────────────────


def test_save_then_load_roundtrip(kv_dir: Path):
    """The sprint-chain invariant: whatever save persists, load reads back."""
    tick_output = {
        "actions_taken": ["x"],
        "errors": [],
        "state": {"tasks": {"t1": {"status": "InProgress"}}},
        "polled_at": "2026-04-15T10:00:00Z",
        "interventions": {"a1": {"count": 3}},
    }
    save_tick_state.execute({"sprint_id": "roundtrip", "tick_result": tick_output})
    loaded = load_tick_state.execute(
        {
            "sprint_id": "roundtrip",
            "repo": "o/r",
            "stall_threshold_m": 20,
            "token_env": "GITHUB_TOKEN",
            "shell_url": "",
        }
    )
    assert loaded["state"] == tick_output["state"]
    assert loaded["since"] == tick_output["polled_at"]
    assert loaded["interventions"] == tick_output["interventions"]
