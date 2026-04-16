#!/usr/bin/env python3
"""Load persisted sprint-tick state from caloron's KV directory.

Called as the first stage of ``sprint_tick_stateful.json``. Reads the
previously-saved state for a sprint (keyed by ``sprint_id``) and fans
it out as top-level fields so the downstream reshape can feed
sprint_tick_core without further glue.

Input:
  { sprint_id: Text, repo: Text, stall_threshold_m: Number,
    token_env: Text, shell_url: Text, host: Text }

Output:
  { sprint_id: Text, repo: Text, stall_threshold_m: Number,
    token_env: Text, shell_url: Text, host: Text,
    state: Any, agents: Any, interventions: Any, since: Text }

Effects: [Fallible]

State lives under ``$CALORON_KV_DIR`` (default ``$HOME/.caloron/kv``),
one JSON file per sprint namespaced by ``sprint_id``. Keeps sprint
persistence in caloron's existing storage domain rather than splitting
it across Noether's KV store.

``host`` (added v0.4.2) passes through unchanged to the downstream
github_* stages so the same composition can target either GitHub or a
self-hosted Gitea — caller controls which by setting the input field.
Default is empty string, which the github stages interpret as
``https://api.github.com``.
"""

import json
import os
from pathlib import Path


def _kv_dir() -> Path:
    override = os.environ.get("CALORON_KV_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("HOME", "/tmp")) / ".caloron" / "kv"


def _load_file(sprint_id: str) -> dict:
    path = _kv_dir() / f"{sprint_id}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def execute(input: dict) -> dict:
    sprint_id = str(input.get("sprint_id", ""))
    if not sprint_id:
        raise ValueError("load_tick_state: 'sprint_id' is required")

    persisted = _load_file(sprint_id)
    # Merge: persisted state provides {state, agents, interventions, since};
    # the outer input provides the rest. Outer wins on conflict so a
    # caller can override state (useful for testing and migration).
    return {
        "sprint_id": sprint_id,
        "repo": str(input.get("repo", "")),
        "stall_threshold_m": int(input.get("stall_threshold_m", 20)),
        "token_env": str(input.get("token_env", "GITHUB_TOKEN")),
        "shell_url": str(input.get("shell_url", "")),
        # Pass-through for the github_* stages downstream. Empty string
        # is the github stages' "use api.github.com" sentinel; callers
        # targeting Gitea pass the API root explicitly.
        "host": str(input.get("host", "")),
        "state": input.get("state") or persisted.get("state", {"tasks": {}}),
        "agents": input.get("agents") or persisted.get("agents", {}),
        "interventions": (
            input.get("interventions") or persisted.get("interventions", {})
        ),
        "since": str(input.get("since") or persisted.get("since", "")),
    }
