#!/usr/bin/env python3
"""Review PO — turn dev tasks into reviewer-assignable checks.

Input:  { tasks: List[Record], design_doc: Text, framework?: Text }
Output: { design_doc: Text, tasks: List[Record], review_checks: List[Record] }

Preserves design_doc + tasks so the terminal flatten stage can merge
review checks back into a single tasks list without re-reading upstream
state. Stage is hermetic; everything needed at runtime lives in this file.
"""



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
    tasks = input.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("review_po: 'tasks' must be a non-empty list")
    design_doc = str(input.get("design_doc") or "")
    framework = str(input.get("framework") or "claude-code")

    checks = []
    for t in tasks:
        tid = t.get("id")
        if not tid:
            raise ValueError("review_po: every task needs an 'id'")
        is_tests = tid.startswith("tests-")
        focus = "test coverage vs. design contract" if is_tests else "correctness vs. interface"
        checks.append(
            {
                "id": f"review-{tid}",
                "reviews": tid,
                "focus": focus,
                "agent_prompt": _prompt_for(t, design_doc, focus),
                "framework": framework,
            }
        )
    return {
        "design_doc": design_doc,
        "tasks": tasks,
        "review_checks": checks,
    }

