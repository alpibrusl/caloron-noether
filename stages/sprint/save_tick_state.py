#!/usr/bin/env python3
"""Persist sprint-tick result to caloron's KV directory.

Called as the terminal stage of ``sprint_tick_stateful.json``. Takes
the rich tick result from sprint_tick_core plus the sprint_id (carried
through the scope), writes the forward-carry fields to disk, and
returns a summary of what happened.

Input:
  { sprint_id: Text, tick_result: Record {
      actions_taken: List<Text>, errors: List<Text>,
      state: Any, polled_at: Text, interventions: Any } }

Output:
  { actions_taken: List<Text>, errors: List<Text>,
    persisted_path: Text }

Effects: [Fallible]
"""

import json
import os
from pathlib import Path


def _kv_dir() -> Path:
    override = os.environ.get("CALORON_KV_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("HOME", "/tmp")) / ".caloron" / "kv"


def execute(input: dict) -> dict:
    sprint_id = str(input.get("sprint_id", ""))
    if not sprint_id:
        raise ValueError("save_tick_state: 'sprint_id' is required")

    tick = input.get("tick_result") or {}
    payload = {
        "state": tick.get("state", {}),
        "interventions": tick.get("interventions", {}),
        "since": tick.get("polled_at", ""),
        # ``agents`` is sent by the caller each tick (scheduler-provided
        # roster), not persisted — the agents dict is environment state,
        # not derived tick state.
    }

    target_dir = _kv_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{sprint_id}.json"
    # Atomic write — avoid half-written files if the process dies.
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, target)

    return {
        "actions_taken": tick.get("actions_taken", []),
        "errors": tick.get("errors", []),
        "persisted_path": str(target),
    }
