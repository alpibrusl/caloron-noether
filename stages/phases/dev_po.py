#!/usr/bin/env python3
"""Dev PO — turn architect components into concrete agent tasks.

Input:  { components: List[Record], design_doc: Text, risks: List[Text],
          sprint_id?: Text, framework?: Text }
Output: { design_doc: Text, components: List[Record], risks: List[Text],
          tasks: List[Record] }

Carries the architect fields through so downstream phases can read them.
Stage is hermetic; everything needed at runtime lives in this file.
"""

import re


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _tasks_for(component: dict, framework: str) -> list:
    slug = _slug(component["name"])
    return [
        {
            "id": f"impl-{slug}",
            "title": f"Implement {component['name']}",
            "depends_on": [],
            "agent_prompt": (
                f"Implement the component '{component['name']}'.\n\n"
                f"Purpose: {component.get('purpose', '')}\n"
                f"Interface: {component.get('interface', '')}\n\n"
                "Create the minimum viable implementation with clear names "
                "and no speculative abstractions."
            ),
            "framework": framework,
            "component": component["name"],
        },
        {
            "id": f"tests-{slug}",
            "title": f"Tests for {component['name']}",
            "depends_on": [f"impl-{slug}"],
            "agent_prompt": (
                f"Write tests for '{component['name']}' covering the happy path and "
                "at least one edge case based on the interface documented in the "
                "design doc."
            ),
            "framework": framework,
            "component": component["name"],
        },
    ]


def execute(input: dict) -> dict:
    raw = input.get("components")
    if not isinstance(raw, list) or not raw:
        raise ValueError("dev_po: 'components' must be a non-empty list")
    required = {"name", "purpose", "interface"}
    for c in raw:
        missing = required - set(c.keys())
        if missing:
            raise ValueError(f"dev_po: component missing fields: {sorted(missing)}")
    framework = str(input.get("framework") or "claude-code")

    tasks: list = []
    for c in raw:
        tasks.extend(_tasks_for(c, framework))
    return {
        "design_doc": str(input.get("design_doc") or ""),
        "components": raw,
        "risks": list(input.get("risks") or []),
        "tasks": tasks,
    }

