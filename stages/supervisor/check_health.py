#!/usr/bin/env python3
"""Classify agent health from heartbeat data.

Input:
  { agents: Map<agent_id, { last_heartbeat_at, task_started_at }>,
    stall_threshold_m: Number }
Output:
  { results: List<{ agent_id, status, minutes_since }> }

Pure stage.
"""
from datetime import UTC, datetime


def execute(input: dict) -> dict:
    data = input
    agents = data.get("agents", {})
    threshold = data.get("stall_threshold_m", 20)
    now = datetime.now(UTC)

    results = []
    for agent_id, info in agents.items():
        hb = info.get("last_heartbeat_at")
        started = info.get("task_started_at")

        if hb is None:
            if started:
                start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                if (now - start_dt).total_seconds() > 120:
                    results.append({"agent_id": agent_id, "status": "missing", "minutes_since": 0})
                else:
                    results.append({"agent_id": agent_id, "status": "healthy", "minutes_since": 0})
            else:
                results.append({"agent_id": agent_id, "status": "unknown", "minutes_since": 0})
        else:
            hb_dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
            minutes = (now - hb_dt).total_seconds() / 60
            if minutes > threshold:
                results.append({"agent_id": agent_id, "status": "stalled", "minutes_since": round(minutes)})
            else:
                results.append({"agent_id": agent_id, "status": "healthy", "minutes_since": round(minutes)})

    return {"results": results}
