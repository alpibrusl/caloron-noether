#!/usr/bin/env python3
"""DAG evaluator — advance task states based on GitHub events.

Input:  { state: DagState, events: List<Event> }
Output: { state: DagState, actions: List<Action> }

Pure stage: no side effects, fully deterministic.
"""
import sys, json
from datetime import datetime, timezone

data = json.load(sys.stdin)
state = data["state"]
events = data.get("events", [])
stall_threshold_m = data.get("stall_threshold_m", 20)

tasks = state["tasks"]
actions = []
now = datetime.now(timezone.utc).isoformat()

# --- Process each event ---
for event in events:
    etype = event.get("type", "")
    issue_number = event.get("issue_number")
    pr_number = event.get("pr_number")
    actor = event.get("actor", "")
    label = event.get("label", "")

    if etype == "issue_opened" and "caloron:task" in event.get("labels", []):
        # Find a Ready task without an issue and assign it
        for tid, task in tasks.items():
            if task["status"] == "Ready" and task.get("issue_number") is None:
                task["issue_number"] = issue_number
                task["status"] = "InProgress"
                task["started_at"] = now
                actions.append({
                    "type": "spawn_agent",
                    "task_id": tid,
                    "agent_id": task.get("agent_id", tid),
                    "issue_number": issue_number,
                })
                break

    elif etype == "pr_opened":
        # Find the task linked to this PR's issue
        linked_issue = event.get("linked_issue")
        for tid, task in tasks.items():
            if task.get("issue_number") == linked_issue and task["status"] == "InProgress":
                task["status"] = "InReview"
                task["pr_number"] = pr_number
                actions.append({
                    "type": "submit_pr_for_review",
                    "task_id": tid,
                    "pr_number": pr_number,
                    "reviewer_id": task.get("reviewer_id"),
                })
                break

    elif etype == "pr_review_submitted":
        review_state = event.get("review_state", "")
        for tid, task in tasks.items():
            if task.get("pr_number") == pr_number and task["status"] == "InReview":
                if review_state == "approved":
                    actions.append({
                        "type": "merge_pr",
                        "task_id": tid,
                        "pr_number": pr_number,
                    })
                elif review_state == "changes_requested":
                    task["status"] = "InProgress"
                    actions.append({
                        "type": "notify_agent",
                        "task_id": tid,
                        "agent_id": task.get("agent_id"),
                        "message": "Changes requested on your PR.",
                    })
                break

    elif etype == "pr_merged":
        for tid, task in tasks.items():
            if task.get("pr_number") == pr_number:
                task["status"] = "Done"
                task["completed_at"] = now
                actions.append({
                    "type": "mark_done",
                    "task_id": tid,
                    "issue_number": task.get("issue_number"),
                    "pr_number": pr_number,
                })
                break

    elif etype == "pr_closed":
        for tid, task in tasks.items():
            if task.get("pr_number") == pr_number and task["status"] == "InReview":
                task["status"] = "InProgress"
                task["pr_number"] = None
                actions.append({
                    "type": "notify_agent",
                    "task_id": tid,
                    "agent_id": task.get("agent_id"),
                    "message": "PR closed without merge. Please rework.",
                })
                break

# --- Unblock tasks whose dependencies are all Done ---
for tid, task in tasks.items():
    if task["status"] == "Pending":
        deps = task.get("depends_on", [])
        if all(tasks.get(dep, {}).get("status") == "Done" for dep in deps):
            task["status"] = "Ready"

# --- Check for stalls ---
for tid, task in tasks.items():
    if task["status"] == "InProgress" and task.get("started_at"):
        started = datetime.fromisoformat(task["started_at"].replace("Z", "+00:00"))
        elapsed_m = (datetime.now(timezone.utc) - started).total_seconds() / 60
        if elapsed_m > stall_threshold_m:
            interventions = task.get("intervention_count", 0)
            if interventions == 0:
                actions.append({
                    "type": "escalate",
                    "task_id": tid,
                    "agent_id": task.get("agent_id"),
                    "reason": f"No activity for {int(elapsed_m)} minutes",
                    "action": "probe",
                })
            elif interventions == 1:
                actions.append({
                    "type": "escalate",
                    "task_id": tid,
                    "agent_id": task.get("agent_id"),
                    "reason": f"Stalled after probe ({int(elapsed_m)} min)",
                    "action": "restart",
                })
            else:
                actions.append({
                    "type": "escalate",
                    "task_id": tid,
                    "agent_id": task.get("agent_id"),
                    "reason": f"Repeated stall ({interventions} interventions)",
                    "action": "escalate_human",
                })
            task["intervention_count"] = interventions + 1

state["tasks"] = tasks
json.dump({"state": state, "actions": actions}, sys.stdout)
