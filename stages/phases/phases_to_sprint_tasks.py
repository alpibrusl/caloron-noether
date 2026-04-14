#!/usr/bin/env python3
"""Terminal flatten stage — merge phase outputs into a single task list.

Input:  { tasks: List[Record], review_checks: List[Record], design_doc: Text }
Output: { tasks: List[Record] }

Effects: [Pure]

Bridges the gap between the multi-phase composition shape (tasks +
review_checks) and the single-list shape the caloron orchestrator
consumes via ``CALORON_PRECOMPUTED_TASKS``. Each review check becomes
a task whose ``depends_on`` points at the task it reviews, so reviewers
run only after the implementation / tests task they cover.

This is the *only* stage that knows about phase internals — future
phases (UX, design, deploy) only need updates here, not in the caloron
CLI. Keep it small; if this grows complex, that's the signal to move
to Noether's Let operator for phase composition instead.
"""

from __future__ import annotations

import json
import os
import sys


def _check_to_task(check: dict) -> dict:
    """Convert a ReviewCheck dict into a sprint-task dict."""
    return {
        "id": check["id"],
        "title": f"Review {check.get('reviews', '?')} — {check.get('focus', '')}".strip(),
        "depends_on": [check["reviews"]] if check.get("reviews") else [],
        "agent_prompt": check.get("agent_prompt", ""),
        "framework": check.get("framework", "claude-code"),
    }


def execute(input: dict) -> dict:
    """Stage entry point."""
    tasks = input.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("phases_to_sprint_tasks: 'tasks' must be a non-empty list")
    checks = input.get("review_checks") or []
    if not isinstance(checks, list):
        raise ValueError("phases_to_sprint_tasks: 'review_checks' must be a list")

    merged: list[dict] = list(tasks)
    seen = {t["id"] for t in merged if "id" in t}
    for c in checks:
        task = _check_to_task(c)
        if task["id"] in seen:
            raise ValueError(
                f"phases_to_sprint_tasks: duplicate task id {task['id']!r} "
                "(a review check collides with a dev task)"
            )
        seen.add(task["id"])
        merged.append(task)

    return {"tasks": merged}


if __name__ == "__main__":
    data = json.load(sys.stdin) if not os.isatty(0) else {}
    json.dump(execute(data), sys.stdout)
