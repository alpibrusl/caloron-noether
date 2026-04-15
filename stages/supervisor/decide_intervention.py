#!/usr/bin/env python3
"""Decide what intervention to take for unhealthy agents.

Input:
  { results: List<{ agent_id, status, minutes_since }>,
    interventions: Map<agent_id, Number> }
Output:
  { actions: List<{ agent_id, action, reason }>,
    updated_interventions: Map<agent_id, Number> }

Pure stage.
"""


def execute(input: dict) -> dict:
    data = input
    results = data.get("results", [])
    interventions = data.get("interventions", {})

    actions = []

    for r in results:
        agent_id = r["agent_id"]
        status = r["status"]
        count = interventions.get(agent_id, 0)

        if status == "healthy":
            continue
        elif status == "missing":
            actions.append({
                "agent_id": agent_id,
                "action": "escalate_human",
                "reason": "Agent process missing (no heartbeat ever received)",
            })
            interventions[agent_id] = count + 1
        elif status == "stalled":
            if count == 0:
                actions.append({
                    "agent_id": agent_id,
                    "action": "probe",
                    "reason": f"No heartbeat for {r['minutes_since']} minutes",
                })
            elif count == 1:
                actions.append({
                    "agent_id": agent_id,
                    "action": "restart",
                    "reason": f"Still stalled after probe ({r['minutes_since']} min)",
                })
            else:
                actions.append({
                    "agent_id": agent_id,
                    "action": "escalate_human",
                    "reason": f"Stalled after {count} interventions",
                })
            interventions[agent_id] = count + 1

    return {
        "actions": actions,
        "updated_interventions": interventions,
    }
