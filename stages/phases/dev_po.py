#!/usr/bin/env python3
"""Dev PO — turn architect components into concrete agent tasks.

Input:  { components: List[Record], design_doc: Text, risks: List[Text],
          sprint_id?: Text, framework?: Text }
Output: { design_doc: Text, components: List[Record], risks: List[Text],
          tasks: List[Record] }

Same provider chain as architect_po — see _llm.py. Falls back to a
deterministic template task layout when no LLM is available.
register_phases.sh concatenates _llm.py into this file's
implementation at registration time so the stage stays hermetic
when executed inside Noether.
"""

import json as _json
import re

from stages.phases._llm import call_llm


def _parse_json_object(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = _json.loads(match.group())
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _validate_tasks(data: dict, components: list) -> bool:
    if not isinstance(data, dict):
        return False
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return False
    component_names = {c["name"] for c in components}
    for t in tasks:
        if not isinstance(t, dict):
            return False
        for key in ("id", "title", "agent_prompt"):
            if not isinstance(t.get(key), str) or not t.get(key):
                return False
        if not isinstance(t.get("depends_on", []), list):
            return False
        comp = t.get("component")
        if comp and comp not in component_names:
            return False
    return True


def _build_prompt(components: list, design_doc: str, framework: str) -> str:
    comp_lines = [
        f"- {c['name']}: {c['purpose']} (interface: {c['interface']})"
        for c in components
    ]
    return (
        "You are the dev PO in a multi-role software sprint. Given the "
        "architect's components and design doc below, emit concrete tasks "
        "for implementation agents.\n\n"
        "For each component, emit an `impl-<slug>` task (no depends_on) and "
        "a `tests-<slug>` task (depends_on the impl task). Write agent_prompt "
        "to be directly usable by a coding agent: include file paths you'd "
        "expect, the function/class to create, and concrete behaviours to "
        "implement — not vague goals.\n\n"
        "Return ONLY a single JSON object with this exact shape, no prose:\n"
        "{\n"
        '  "tasks": [\n'
        "    {\n"
        '      "id": "impl-<slug>",\n'
        '      "title": "...",\n'
        '      "depends_on": [],\n'
        '      "agent_prompt": "...",\n'
        '      "framework": "' + framework + '",\n'
        '      "component": "<ComponentName>"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "<design_doc>\n"
        f"{design_doc.strip()}\n"
        "</design_doc>\n"
        "<components>\n"
        + "\n".join(comp_lines)
        + "\n</components>"
    )


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _template_tasks(components: list, framework: str) -> list:
    tasks: list = []
    for c in components:
        slug = _slug(c["name"])
        tasks.append(
            {
                "id": f"impl-{slug}",
                "title": f"Implement {c['name']}",
                "depends_on": [],
                "agent_prompt": (
                    f"Implement the component '{c['name']}'.\n\n"
                    f"Purpose: {c.get('purpose', '')}\n"
                    f"Interface: {c.get('interface', '')}\n\n"
                    "Create the minimum viable implementation with clear "
                    "names and no speculative abstractions."
                ),
                "framework": framework,
                "component": c["name"],
            }
        )
        tasks.append(
            {
                "id": f"tests-{slug}",
                "title": f"Tests for {c['name']}",
                "depends_on": [f"impl-{slug}"],
                "agent_prompt": (
                    f"Write tests for '{c['name']}' covering the happy path and "
                    "at least one edge case based on the interface documented "
                    "in the design doc."
                ),
                "framework": framework,
                "component": c["name"],
            }
        )
    return tasks


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
    design_doc = str(input.get("design_doc") or "")

    tasks = None
    llm_text = call_llm(_build_prompt(raw, design_doc, framework))
    if llm_text:
        parsed = _parse_json_object(llm_text)
        if parsed and _validate_tasks(parsed, raw):
            tasks = parsed["tasks"]

    if tasks is None:
        tasks = _template_tasks(raw, framework)

    return {
        "design_doc": design_doc,
        "components": raw,
        "risks": list(input.get("risks") or []),
        "tasks": tasks,
    }
