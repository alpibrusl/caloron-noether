#!/usr/bin/env python3
"""Compute sprint KPIs from final DAG state.

Input:  { state: DagState, started_at: Text, ended_at: Text }
Output: { total_tasks, completed_tasks, completion_rate, sprint_days, tasks_per_day,
          escalated_count, blocked_count, avg_interventions }

Pure stage.
"""
from datetime import datetime


def execute(input: dict) -> dict:
    data = input
    tasks = data["state"]["tasks"]
    started_at = data.get("started_at", "")
    ended_at = data.get("ended_at", "")

    total = len(tasks)
    completed = sum(1 for t in tasks.values() if t["status"] == "Done")
    escalated = sum(1 for t in tasks.values() if t["status"] in ("Escalated", "Blocked"))
    blocked = sum(1 for t in tasks.values() if t["status"] == "Blocked")
    total_interventions = sum(t.get("intervention_count", 0) for t in tasks.values())

    completion_rate = completed / total if total > 0 else 0.0
    avg_interventions = total_interventions / total if total > 0 else 0.0

    sprint_days = 0.0
    tasks_per_day = 0.0
    if started_at and ended_at:
        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            sprint_days = (end - start).total_seconds() / 86400
            if sprint_days > 0:
                tasks_per_day = completed / sprint_days
        except Exception:
            pass

    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "completion_rate": round(completion_rate, 3),
        "sprint_days": round(sprint_days, 1),
        "tasks_per_day": round(tasks_per_day, 1),
        "escalated_count": escalated,
        "blocked_count": blocked,
        "total_interventions": total_interventions,
        "avg_interventions": round(avg_interventions, 2),
    }
