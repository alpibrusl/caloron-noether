#!/usr/bin/env python3
"""Review PO — turn dev tasks into reviewer-assignable checks.

Input:  { tasks: List[Record], design_doc: Text, framework: Text }
Output: { review_checks: List[Record] }

Effects: [Pure]

For each implementation task emitted by dev_po, schedules a review
check that depends on it. Test tasks get a separate "test-coverage"
review focused on whether the tests match the design contract. The
review prompts reference the design_doc so reviewers can compare
against the architect's original intent — not just whether the code
runs, but whether it's the *right* code.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root))
from stages.phases.phase_schemas import ReviewCheck  # noqa: E402


def _prompt_for(task: dict, design_doc: str, focus: str) -> str:
    return (
        f"Review task '{task.get('id')}' (titled '{task.get('title')}').\n"
        f"Focus: {focus}.\n\n"
        "Compare the implementation against the design contract below. "
        "Flag any place the code diverges from the stated interface or "
        "purpose, and call out missing edge cases.\n\n"
        "=== Design doc ===\n"
        f"{design_doc}\n"
    )


def execute(input: dict) -> dict:
    """Stage entry point."""
    tasks = input.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("review_po: 'tasks' must be a non-empty list")
    design_doc = str(input.get("design_doc") or "")
    framework = str(input.get("framework") or "claude-code")

    checks: list[ReviewCheck] = []
    for t in tasks:
        tid = t.get("id")
        if not tid:
            raise ValueError("review_po: every task needs an 'id'")
        is_tests = tid.startswith("tests-")
        focus = "test coverage vs. design contract" if is_tests else "correctness vs. interface"
        checks.append(
            ReviewCheck(
                id=f"review-{tid}",
                reviews=tid,
                focus=focus,
                agent_prompt=_prompt_for(t, design_doc, focus),
                framework=framework,
            )
        )
    return {"review_checks": [c.to_dict() for c in checks]}


if __name__ == "__main__":
    data = json.load(sys.stdin) if not os.isatty(0) else {}
    json.dump(execute(data), sys.stdout)
