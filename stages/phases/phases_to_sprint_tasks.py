#!/usr/bin/env python3
"""Terminal flatten stage — merge phase outputs into a single task list.

Input:  { tasks: List[Record], review_checks: List[Record], design_doc: Text }
Output: { tasks: List[Record] }

Each review check becomes a task whose depends_on points at the task it
reviews, so reviewers run only after the implementation / tests task
they cover. This is the one place in the codebase that knows about
phase internals — future phases only need updates here, not in the CLI.
Stage is hermetic; everything needed at runtime lives in this file.
"""



def _check_to_task(check: dict) -> dict:
    return {
        "id": check["id"],
        "title": f"Review {check.get('reviews', '?')} — {check.get('focus', '')}".strip(),
        "depends_on": [check["reviews"]] if check.get("reviews") else [],
        "agent_prompt": check.get("agent_prompt", ""),
        "framework": check.get("framework", "claude-code"),
    }


def execute(input: dict) -> dict:
    tasks = input.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("phases_to_sprint_tasks: 'tasks' must be a non-empty list")
    checks = input.get("review_checks") or []
    if not isinstance(checks, list):
        raise ValueError("phases_to_sprint_tasks: 'review_checks' must be a list")

    merged = list(tasks)
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

