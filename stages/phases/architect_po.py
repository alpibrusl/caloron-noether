#!/usr/bin/env python3
"""Architect PO — decompose a goal into components + risks.

Input:  { goal: Text, constraints: Text }
Output: { design_doc: Text, components: List[Record], risks: List[Text] }

Effects: [Llm, NonDeterministic]

Template-based fallback (no LLM dependency) splits the goal into candidate
components by looking for verbs and noun phrases. The real production
version should call an LLM with a structured prompt and validate against
ArchitectOutput. The schema validation is the load-bearing part — keep it.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root))
from stages.phases.phase_schemas import ArchitectOutput, Component  # noqa: E402


def _template_decompose(goal: str, constraints: str) -> ArchitectOutput:
    """Very small template-only decomposition. Deterministic for tests."""
    # Extract capitalized / quoted nouns as component candidates.
    # Falls back to a single 'core' component when the goal is one liner.
    candidates = re.findall(r"\b([A-Z][a-zA-Z_]{2,})\b", goal)
    seen: set[str] = set()
    names: list[str] = []
    for c in candidates:
        if c.lower() not in seen:
            seen.add(c.lower())
            names.append(c)
    if not names:
        names = ["Core"]

    components = [
        Component(
            name=n,
            purpose=f"Implements the '{n}' responsibility derived from the goal.",
            interface=f"Public surface for {n}; see design_doc for contract.",
        )
        for n in names[:5]
    ]

    design_doc_lines = [
        f"# Design — {goal.strip().splitlines()[0][:80]}",
        "",
        "## Goal",
        goal.strip(),
        "",
    ]
    if constraints.strip():
        design_doc_lines += ["## Constraints", constraints.strip(), ""]
    design_doc_lines += ["## Components"]
    for c in components:
        design_doc_lines.append(f"- **{c.name}** — {c.purpose}")
    design_doc = "\n".join(design_doc_lines)

    risks: list[str] = []
    if len(components) == 1:
        risks.append(
            "Only one component identified — double-check the decomposition "
            "is not hiding a coupled concern."
        )
    if "security" not in goal.lower() and "auth" in goal.lower():
        risks.append("Auth mentioned without explicit security constraints.")

    return ArchitectOutput(design_doc=design_doc, components=components, risks=risks)


def execute(input: dict) -> dict:
    """Stage entry point (required by noether stage sync)."""
    goal = str(input.get("goal", ""))
    constraints = str(input.get("constraints", ""))
    if not goal.strip():
        raise ValueError("architect_po: 'goal' must be non-empty")
    output = _template_decompose(goal, constraints)
    return output.to_dict()


if __name__ == "__main__":
    # Legacy stdin/stdout invocation (used by run_noether_stage in the
    # caloron orchestrator). Prefer `noether run` for graph-level execution.
    data = json.load(sys.stdin) if not os.isatty(0) else {}
    json.dump(execute(data), sys.stdout)
