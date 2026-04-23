"""Runtime-shape tests for the orchestrator type aliases.

``TypedDict`` is a static-only concept — at runtime, instances are
plain ``dict``. These tests do two things:

1. **Runtime:** lock in the structural agreements at test-collection
   time (``get_type_hints`` assertions, shape-round-trip smokes).
2. **Static:** the ``TYPE_CHECKING`` block at the bottom serves as
   pyright's regression guard for the typed orchestrator functions —
   this file is in ``pyrightconfig.json::include`` alongside
   ``orchestrator/types_.py``, so any change that breaks the declared
   signatures of ``_enforce_required_skills`` / ``_resolved_skills_for``
   surfaces here during the ``Python Types (pyright allowlist)`` CI
   job even though ``orchestrator/orchestrator.py`` itself isn't yet
   in the allowlist. See issue #17 for the broader rollout.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, get_type_hints

# sys.path shim: orchestrator-side modules use bare-name imports
# (``from agent_configurator import …``) — they need the orchestrator
# dir on sys.path to resolve. We add both the repo root (so package
# paths like ``orchestrator.orchestrator`` work for the TYPE_CHECKING
# block below) and the orchestrator dir (for our own bare-name
# ``from types_ import …``).
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

    def test_only_id_and_title_are_required(self):
        # After the #17 Pass 2 split, ``id`` and ``title`` are required
        # (inherited from ``_RequiredTaskFields``); everything else is
        # optional. Pins the required-field set so a future refactor
        # that moves ``id`` or ``title`` into the optional bucket — and
        # would silently re-enable the "Could not access item" class of
        # pyright errors in ``orchestrator.py`` — fails here first.
        hints = get_type_hints(TaskDict)
        # Minimum valid instance.
        t: TaskDict = {"id": "t1", "title": "sample"}
        assert t["id"] == "t1"
        # Required-ness is exposed via the class-level sets, not the
        # annotations dict.
        assert TaskDict.__required_keys__ == {"id", "title"}
        # All the optional-at-rest fields are still in the annotations.
        assert "depends_on" in hints
        assert "agentspec" in hints

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
    # Compile-time assertion that TaskDict / BlockedTaskDict flow
    # through the orchestrator's typed functions correctly. The block
    # is never executed at runtime (``TYPE_CHECKING`` is False there),
    # but pyright evaluates it during the CI ``python-types`` job —
    # this file is in ``pyrightconfig.json::include`` — so any refactor
    # that drifts the typed signatures of ``_enforce_required_skills``
    # or ``_resolved_skills_for`` surfaces as a CI failure here.
    #
    # This is the load-bearing mechanism for keeping the annotations
    # honest until ``orchestrator.orchestrator`` itself joins the
    # pyright allowlist (tracked as Pass 2 on #17).
    from orchestrator.orchestrator import (
        _enforce_required_skills,
        _resolved_skills_for,
    )

    _task: TaskDict = {"id": "x", "title": "y"}
    _skills: set[str] = _resolved_skills_for(_task)
    _runnable: list[TaskDict]
    _blocked: list[BlockedTaskDict]
    _runnable, _blocked = _enforce_required_skills([_task])
