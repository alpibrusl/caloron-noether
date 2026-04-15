#!/usr/bin/env python3
"""Return tasks that are Ready (dependencies satisfied, not yet started).

Input:  { state: DagState }
Output: { ready_tasks: List<Record> }

Pure stage.
"""


def execute(input: dict) -> dict:
    data = input
    tasks = data["state"]["tasks"]

    ready = []
    for tid, task in tasks.items():
        if task["status"] == "Ready":
            ready.append({
                "task_id": tid,
                "title": task.get("title", ""),
                "agent_id": task.get("agent_id", ""),
                "issue_number": task.get("issue_number"),
            })

    return {"ready_tasks": ready}
