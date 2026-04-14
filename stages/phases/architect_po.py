#!/usr/bin/env python3
"""Architect PO — decompose a goal into components + risks.

Input:  { goal: Text, constraints: Text }
Output: { design_doc: Text, components: List[Record], risks: List[Text] }

Template-based fallback (no LLM dependency) splits the goal into candidate
components by looking for capitalised noun phrases. Stages are hermetic by
Noether convention — everything needed at runtime lives in this file.
"""

import re


def _decompose(goal: str, constraints: str) -> dict:
    candidates = re.findall(r"\b([A-Z][a-zA-Z_]{2,})\b", goal)
    seen: set = set()
    names = []
    for c in candidates:
        if c.lower() not in seen:
            seen.add(c.lower())
            names.append(c)
    if not names:
        names = ["Core"]

    components = [
        {
            "name": n,
            "purpose": f"Implements the '{n}' responsibility derived from the goal.",
            "interface": f"Public surface for {n}; see design_doc for contract.",
        }
        for n in names[:5]
    ]

    lines = [
        f"# Design — {goal.strip().splitlines()[0][:80]}",
        "",
        "## Goal",
        goal.strip(),
        "",
    ]
    if constraints.strip():
        lines += ["## Constraints", constraints.strip(), ""]
    lines += ["## Components"]
    for c in components:
        lines.append(f"- **{c['name']}** — {c['purpose']}")
    design_doc = "\n".join(lines)

    risks = []
    if len(components) == 1:
        risks.append(
            "Only one component identified — double-check the decomposition "
            "is not hiding a coupled concern."
        )
    if "security" not in goal.lower() and "auth" in goal.lower():
        risks.append("Auth mentioned without explicit security constraints.")

    return {"design_doc": design_doc, "components": components, "risks": risks}


def execute(input: dict) -> dict:
    goal = str(input.get("goal", ""))
    constraints = str(input.get("constraints", ""))
    if not goal.strip():
        raise ValueError("architect_po: 'goal' must be non-empty")
    return _decompose(goal, constraints)

