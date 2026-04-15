#!/usr/bin/env python3
"""Execute actions produced by dag_evaluate and decide_intervention.

Dispatches each action to the appropriate GitHub API call or shell endpoint.

Input:
  {
    repo: Text,
    token_env: Text,
    shell_url: Text,
    dag_actions: List<Record>,
    supervisor_actions: List<Record>,
    dag_complete: Bool
  }
Output:
  { actions_taken: List<Text>, errors: List<Text> }

Effects: [Network, Fallible]
"""
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def execute(input: dict) -> dict:
    data = input
    repo = data.get("repo", "")
    token = os.environ.get(data.get("token_env", "GITHUB_TOKEN"), "")
    shell_url = data.get("shell_url", "http://localhost:7710")
    dag_actions = data.get("dag_actions", [])
    supervisor_actions = data.get("supervisor_actions", [])
    sprint_id = data.get("sprint_id", "")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }

    actions_taken = []
    errors = []

    def gh_post(path, body):
        req = Request(
            f"https://api.github.com/repos/{repo}{path}",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            errors.append(f"GitHub POST {path}: {e}")
            return None

    def gh_put(path, body=None):
        req = Request(
            f"https://api.github.com/repos/{repo}{path}",
            data=json.dumps(body or {}).encode(),
            headers=headers,
            method="PUT",
        )
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            errors.append(f"GitHub PUT {path}: {e}")
            return None

    def shell_post(path, body):
        req = Request(
            f"{shell_url}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read())
        except Exception as e:
            errors.append(f"Shell POST {path}: {e}")
            return None

    # Process DAG actions
    for action in dag_actions:
        atype = action.get("type", "")

        if atype == "spawn_agent":
            task_id = action.get("task_id", "")
            agent_id = action.get("agent_id", "")
            issue_number = action.get("issue_number")

            # Post assignment comment
            if issue_number:
                gh_post(f"/issues/{issue_number}/comments", {
                    "body": f"@caloron-agent-{agent_id} has been assigned this task."
                })
                gh_post(f"/issues/{issue_number}/labels", {
                    "labels": ["caloron:assigned"]
                })

            # Spawn agent via shell
            result = shell_post("/spawn", {
                "sprint_id": sprint_id,
                "task_id": task_id,
                "agent_id": agent_id,
                "repo": repo,
            })
            if result and result.get("ok"):
                actions_taken.append(f"spawn:{agent_id} (pid={result.get('pid')})")
            else:
                actions_taken.append(f"spawn:{agent_id} FAILED")

        elif atype == "merge_pr":
            pr_number = action.get("pr_number")
            if pr_number:
                result = gh_put(f"/pulls/{pr_number}/merge")
                if result:
                    actions_taken.append(f"merge:PR#{pr_number}")

                    # Close linked issue
                    issue_number = action.get("issue_number")
                    if issue_number:
                        gh_post(f"/issues/{issue_number}/comments", {
                            "body": f"Completed via PR #{pr_number}"
                        })
                        gh_post(f"/issues/{issue_number}/labels", {
                            "labels": ["caloron:done"]
                        })

        elif atype == "mark_done":
            issue_number = action.get("issue_number")
            if issue_number:
                gh_post(f"/issues/{issue_number}/labels", {
                    "labels": ["caloron:done"]
                })
                actions_taken.append(f"done:#{issue_number}")

        elif atype == "notify_agent":
            agent_id = action.get("agent_id", "")
            message = action.get("message", "")
            # Find the agent's issue (would need issue_number in action)
            actions_taken.append(f"notify:{agent_id}")

        elif atype == "submit_pr_for_review":
            pr_number = action.get("pr_number")
            if pr_number:
                gh_post(f"/issues/{pr_number}/labels", {
                    "labels": ["caloron:review-pending"]
                })
                actions_taken.append(f"review:PR#{pr_number}")

        elif atype == "escalate":
            agent_id = action.get("agent_id", "")
            reason = action.get("reason", "")
            escalate_action = action.get("action", "probe")

            if escalate_action == "escalate_human":
                result = gh_post("/issues", {
                    "title": f"Escalation: {agent_id} — {reason}",
                    "body": f"## Human intervention required\n\n**Agent:** {agent_id}\n**Reason:** {reason}\n\nComment `resolved` when fixed.",
                    "labels": ["caloron:escalated"],
                })
                actions_taken.append(f"escalate:{agent_id}")

    # Process supervisor actions
    for action in supervisor_actions:
        agent_id = action.get("agent_id", "")
        sup_action = action.get("action", "")
        reason = action.get("reason", "")

        if sup_action == "probe":
            actions_taken.append(f"probe:{agent_id} ({reason})")
        elif sup_action == "restart":
            # Kill and respawn via shell
            actions_taken.append(f"restart:{agent_id}")
        elif sup_action == "escalate_human":
            gh_post("/issues", {
                "title": f"Escalation: {agent_id}",
                "body": f"**Agent:** {agent_id}\n**Reason:** {reason}",
                "labels": ["caloron:escalated"],
            })
            actions_taken.append(f"escalate:{agent_id}")

    return {
        "actions_taken": actions_taken,
        "errors": errors,
    }
