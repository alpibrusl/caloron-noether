"""Shared TypedDict / dataclass shapes for the orchestrator.

Orchestrator code has historically passed ``dict`` around as the
lingua franca between phase stages, the HR agent, the bridge, and the
main sprint loop. That's fine at runtime — every stage agrees on the
keys — but it gives pyright no way to tell callers and readers which
keys are expected, which are optional, and which are documented
elsewhere.

This module is the **first typed surface**. Types declared here are
the ones the functions listed in ``pyrightconfig.json``'s
``include`` list rely on. Adding a new typed entry point means:

1. Declare the shape here (TypedDict for heterogenous JSON-like
   payloads, ``@dataclass`` only for internal state with invariants).
2. Annotate the function signature using the new type.
3. Add the file to ``include`` in ``pyrightconfig.json``.

Scope is deliberately narrow for this first pass — see issue #17 and
the "Pass 2" section of that plan. ``_enforce_required_skills`` and
``_resolved_skills_for`` are the entry points covered by this batch;
more will move in follow-ups.

## Why TypedDict, not dataclass

The tasks these functions operate on are constructed by JSON-emitting
agents (PO, HR) and passed through Noether stages. They arrive as
dicts at the orchestrator's door. Converting to ``@dataclass`` would
require round-tripping through ``.to_dict()`` / ``.from_dict()`` at
every boundary — a large refactor with marginal correctness gain.
TypedDict documents the shape *without* changing the runtime
representation.
"""

from __future__ import annotations

from typing import TypedDict


class AgentspecBridge(TypedDict, total=False):
    """Optional shape attached to a task when ``agentspec_bridge`` has
    resolved it.

    **Semantic invariant** (not expressed statically): in practice each
    instance has either ``tools`` (resolution succeeded) **or** ``error``
    (resolution failed), not both and not neither. ``total=False``
    permits all four combinations statically — expressing the real
    invariant would require a ``Union[Success, Error]`` shape that
    fragments call-site code without catching a bug that ever occurs in
    practice. Callers should branch on ``"error" in bridge`` and treat
    ``tools`` as meaningful only on the success path.
    """

    tools: list[str]
    error: str


class _RequiredTaskFields(TypedDict):
    """Always-present fields on a task payload.

    Split from ``TaskDict`` so pyright can statically prove ``t["id"]``
    and ``t["title"]`` never KeyError. Every stage that emits a task —
    PO decompose, HR assignment, agentspec bridge — sets both of these;
    they're load-bearing across logging, branch naming, and gitea issue
    titles. If a future stage can't promise them, construct a separate
    partial type rather than loosening this one.
    """

    id: str
    title: str


class TaskDict(_RequiredTaskFields, total=False):
    """The "task" payload that flows from the PO / HR agents through the
    main sprint loop.

    Inherits required ``id`` + ``title`` from ``_RequiredTaskFields``;
    all other fields are declared ``total=False`` because different
    code paths populate different subsets — HR sets ``skills`` and
    maybe ``agentspec``; PO sets ``depends_on``; the bridge adds
    ``tools_used``. Every consumer reads those defensively with
    ``.get()`` or a membership check.

    See ``orchestrator/validation.py`` for the ``id`` invariants.
    """

    depends_on: list[str]
    skills: list[str]
    tools_used: list[str]
    required_skills: list[str]
    framework: str
    agentspec: AgentspecBridge
    # Downstream-populated field: HR / agentspec evolution can append a
    # preamble to this that the agent sees before the main prompt.
    agent_prompt: str


class BlockedTaskDict(TypedDict):
    """Emitted by ``_enforce_required_skills`` for tasks that couldn't
    satisfy their ``required_skills``.

    Callers log these as first-class blockers so the retro captures the
    config gap rather than silently dropping the task. All fields are
    required — this is orchestrator-internal, not agent-provided.
    """

    id: str
    required: list[str]
    resolved: list[str]
    missing: list[str]
    task: TaskDict
