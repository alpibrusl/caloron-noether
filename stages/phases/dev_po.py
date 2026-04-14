#!/usr/bin/env python3
"""Dev PO — turn architect components into concrete agent tasks.

Input:  { components: List[Record], sprint_id: Text, framework: Text }
Output: { tasks: List[Record] }

Effects: [Pure]

Reads ArchitectOutput-shaped `components` and emits one implementation
task plus one test task per component. Keeping this template-based makes
the composition deterministic for tests; swap in an LLM later once the
interface stabilises.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root))
from stages.phases.phase_schemas import Component, DevTask  # noqa: E402


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _tasks_for(component: Component, framework: str) -> list[DevTask]:
    slug = _slug(component.name)
    impl = DevTask(
        id=f"impl-{slug}",
        title=f"Implement {component.name}",
        depends_on=[],
        agent_prompt=(
            f"Implement the component '{component.name}'.\n\n"
            f"Purpose: {component.purpose}\n"
            f"Interface: {component.interface}\n\n"
            "Create the minimum viable implementation with clear names "
            "and no speculative abstractions."
        ),
        framework=framework,
        component=component.name,
    )
    tests = DevTask(
        id=f"tests-{slug}",
        title=f"Tests for {component.name}",
        depends_on=[impl.id],
        agent_prompt=(
            f"Write tests for '{component.name}' covering the happy path and "
            "at least one edge case based on the interface documented in the "
            "design doc."
        ),
        framework=framework,
        component=component.name,
    )
    return [impl, tests]


def execute(input: dict) -> dict:
    """Stage entry point."""
    raw_components = input.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ValueError("dev_po: 'components' must be a non-empty list")
    components = [Component.from_dict(c) for c in raw_components]
    framework = str(input.get("framework") or "claude-code")

    tasks: list[DevTask] = []
    for c in components:
        tasks.extend(_tasks_for(c, framework))
    return {"tasks": [t.to_dict() for t in tasks]}


if __name__ == "__main__":
    data = json.load(sys.stdin) if not os.isatty(0) else {}
    json.dump(execute(data), sys.stdout)
