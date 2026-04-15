#!/usr/bin/env python3
"""Compose a GitHub comment for a supervisor intervention.

Input:  { agent_id: Text, task_title: Text, health_status: Text, action: Text }
Output: { message: Text }

Pure stage (template-based, no LLM needed for structured messages).
"""


def execute(input: dict) -> dict:
    data = input
    agent_id = data["agent_id"]
    task_title = data.get("task_title", "unknown task")
    status = data["health_status"]
    action = data["action"]

    if action == "probe":
        message = (
            f"@caloron-agent-{agent_id} You have had no activity on \"{task_title}\". "
            f"Please respond with your current status. If you are blocked, describe what you need."
        )
    elif action == "restart":
        message = (
            f"Agent `{agent_id}` working on \"{task_title}\" has been stalled. "
            f"The agent will be restarted with the same task context. "
            f"Work in the git worktree is preserved."
        )
    elif action == "escalate_human":
        message = (
            f"## Human intervention required\n\n"
            f"**Agent:** `{agent_id}`\n"
            f"**Task:** {task_title}\n"
            f"**Status:** {status}\n\n"
            f"The supervisor has exhausted automatic recovery options. "
            f"Please investigate and comment `resolved` when fixed, "
            f"or `caloron:take-over` to handle it directly."
        )
    else:
        message = f"Agent `{agent_id}` status: {status}. Action: {action}."

    return {"message": message}
