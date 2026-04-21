"""Runtime-shape tests for the orchestrator type aliases.

``TypedDict`` is a static-only concept — at runtime, instances are
plain ``dict``. These tests don't re-prove pyright's work; instead
they lock in the *structural* agreements that pyright enforces
statically, so a future code reorganisation that breaks the expected
keys fails at test collection time rather than at production runtime.

Pyright-visible typing is verified separately in CI via the
``Python Types (pyright allowlist)`` job. See issue #17 for the
broader rollout plan.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, get_type_hints

# Shim — like tests/test_orchestrator_learnings.py but with the paths
# inserted in the opposite order: we want `orchestrator` to resolve as
# a *package* (so `orchestrator.types_` works) rather than as the bare
# `orchestrator.py` module that the existing orchestrator-side imports
# rely on.  ``insert(0)`` means later calls end up first in sys.path,
# so we insert _ORCH_DIR first and _REPO_ROOT second.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORCH_DIR = _REPO_ROOT / "orchestrator"
for _p in (str(_ORCH_DIR), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from types_ import (  # noqa: E402
    AgentspecBridge,
    BlockedTaskDict,
    TaskDict,
)


class TestTaskDict:
    def test_accepts_minimum_shape(self):
        # Minimum useful task — PO emits at least id + title.
        t: TaskDict = {"id": "task-001", "title": "Do the thing"}
        assert t["id"] == "task-001"
        assert t["title"] == "Do the thing"

    def test_accepts_full_shape(self):
        t: TaskDict = {
            "id": "impl-parser",
            "title": "Implement the parser",
            "depends_on": ["design-parser"],
            "skills": ["file-write", "test-run"],
            "tools_used": ["pytest"],
            "required_skills": ["file-write"],
            "framework": "claude-code",
            "agentspec": {"tools": ["pytest-mcp"]},
            "agent_prompt": "Extra context for this task…",
        }
        # All keys readable as documented.
        assert t.get("depends_on") == ["design-parser"]
        assert t.get("required_skills") == ["file-write"]
        assert t.get("agentspec", {}).get("tools") == ["pytest-mcp"]

    def test_all_fields_are_optional(self):
        # total=False means every key is optional at runtime (and for
        # pyright's get/membership semantics). An empty dict is a
        # legal TaskDict — useful during construction / migration.
        t: TaskDict = {}
        assert dict(t) == {}

    def test_hints_are_strings_or_lists_of_str(self):
        # Sanity: the annotations themselves don't drift. Runtime
        # inspection of the TypedDict class confirms the declared
        # types haven't silently changed type.
        hints = get_type_hints(TaskDict)
        # id, title, framework, agent_prompt are strings.
        assert hints["id"] is str
        assert hints["title"] is str
        assert hints["framework"] is str
        assert hints["agent_prompt"] is str
        # depends_on / skills / tools_used / required_skills are lists of str.
        for key in ("depends_on", "skills", "tools_used", "required_skills"):
            assert hints[key] == list[str], f"{key} hint regressed"


class TestBlockedTaskDict:
    def test_shape_matches_enforce_output(self):
        # Pyright enforces this statically in _enforce_required_skills.
        # Runtime test locks in the set of keys the diagnostic record
        # carries — orchestrator.main() logs these; a field rename
        # without updating the logger would silently drop the info.
        b: BlockedTaskDict = {
            "id": "task-001",
            "required": ["file-write"],
            "resolved": ["file-read"],
            "missing": ["file-write"],
            "task": {"id": "task-001", "title": "Do the thing"},
        }
        assert set(b.keys()) == {"id", "required", "resolved", "missing", "task"}

    def test_blocked_is_fully_required_unlike_task(self):
        # Unlike TaskDict (total=False), BlockedTaskDict is full-total.
        # Missing any field is a type error — pyright catches that
        # statically; runtime confirms the class was declared with
        # every field expected.
        hints = get_type_hints(BlockedTaskDict)
        assert set(hints.keys()) == {"id", "required", "resolved", "missing", "task"}


class TestAgentspecBridge:
    def test_both_fields_optional(self):
        # The agentspec bridge attaches `tools` on success and `error`
        # on failure — it's one or the other in practice, but
        # TypedDict semantics permit any subset.
        empty: AgentspecBridge = {}
        with_tools: AgentspecBridge = {"tools": ["pytest-mcp"]}
        with_error: AgentspecBridge = {"error": "resolver timed out"}

        assert dict(empty) == {}
        assert with_tools.get("tools") == ["pytest-mcp"]
        assert with_error.get("error") == "resolver timed out"


# ── Static-use regression guard ──────────────────────────────────────────


if TYPE_CHECKING:
    # Compile-time assertion that TaskDict flows through the orchestrator's
    # typed functions. Pyright verifies at lint-time; this block is never
    # executed but prevents a refactor from accidentally changing the
    # public types without updating downstream.
    from orchestrator import (
        _enforce_required_skills,
        _resolved_skills_for,
    )

    _task: TaskDict = {"id": "x", "title": "y"}
    _skills: set[str] = _resolved_skills_for(_task)
    _runnable: list[TaskDict]
    _blocked: list[BlockedTaskDict]
    _runnable, _blocked = _enforce_required_skills([_task])
