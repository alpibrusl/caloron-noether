#!/usr/bin/env python3
"""Validate a DAG for structural correctness.

Input:  { dag: DagState }
Output: { valid: Bool, errors: List<Text> }

Pure stage. Checks: no cycles, valid references, unique IDs.
"""
from collections import defaultdict


def execute(input: dict) -> dict:
    data = input
    dag = data["dag"]
    tasks = dag.get("tasks", {})

    errors = []

    # Check unique task IDs (already guaranteed by dict keys, but check for empty)
    if not tasks:
        errors.append("DAG has no tasks")

    # Collect all known task IDs and agent IDs
    task_ids = set(tasks.keys())
    agent_ids = set()
    for t in tasks.values():
        if t.get("agent_id"):
            agent_ids.add(t["agent_id"])

    # Check references
    for tid, task in tasks.items():
        # Check depends_on references exist
        for dep in task.get("depends_on", []):
            if dep not in task_ids:
                errors.append(f"Task '{tid}' depends on unknown task '{dep}'")

        # Check agent_id is present
        if not task.get("agent_id"):
            errors.append(f"Task '{tid}' has no agent_id")

    # Cycle detection (Kahn's algorithm)
    in_degree = {tid: 0 for tid in task_ids}
    adj = defaultdict(list)

    for tid, task in tasks.items():
        for dep in task.get("depends_on", []):
            if dep in task_ids:
                adj[dep].append(tid)
                in_degree[tid] += 1

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    visited = 0

    while queue:
        node = queue.pop()
        visited += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(task_ids):
        cycle_tasks = [tid for tid, deg in in_degree.items() if deg > 0]
        errors.append(f"DAG contains a cycle involving: {', '.join(cycle_tasks)}")

    return {"valid": len(errors) == 0, "errors": errors}
