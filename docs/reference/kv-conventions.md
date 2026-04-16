# State persistence

Caloron has two state stores; here is what lives in each.

## Caloron KV directory (sprint state)

`$CALORON_KV_DIR/<sprint_id>.json`, defaulting to
`~/.caloron/kv/<sprint_id>.json`. One JSON file per sprint, atomic
write via tmp+rename. Used by `sprint_tick_stateful.json` (specifically
the `load_tick_state` / `save_tick_state` stages).

Persisted shape:

```json
{
  "state": { "tasks": { "<task_id>": { "status": "InProgress", ... } } },
  "interventions": { "<agent_id>": { "count": 1 } },
  "since": "2026-04-15T10:00:00Z"
}
```

| Field | Meaning |
|-------|---------|
| `state` | DAG state (task statuses, dependencies, completion times) |
| `interventions` | Per-agent intervention counters used by the supervisor's probe→restart→escalate ladder |
| `since` | Timestamp last polled — passed as `since` to `github_poll_events` next tick |

`agents` is intentionally **not** persisted — it's environment state
the caller (scheduler) supplies fresh each tick.

## Caloron WORK directory (orchestrator-only state)

`orchestrator.py` uses its own filesystem-based store under `$WORK`
(typically `~/.caloron/projects/<name>/workspace/`). This is what the
production CLI path (`caloron sprint`) reads/writes:

| File | Purpose |
|------|---------|
| `learnings.json` | Cumulative sprint history + improvements + last_po_context, fed back into the next sprint's PO prompt |
| `dag.json` | Current sprint's task list |
| `agent_versions.json` | Agent-version store (skill/trait evolution across sprints) |
| `skill_store.json` | Available skills the HR agent draws from |
| `agents/` | Per-task `.agent` manifest files (when AgentSpec is installed) |

These are not used by the Noether composition path. They predate it
and are the production source of truth for the CLI flow.

## Noether's built-in KV store

Noether ships with KV stages (`Store a JSON value under a key` /
`Retrieve a JSON value by key`) that persist to `~/.noether/kv.json`.
Caloron currently does **not** use these — `sprint_tick_stateful.json`
uses caloron's own KV directory instead, to:

1. Match orchestrator.py's existing file-based state model
2. Avoid splitting sprint state across two stores
3. Skip needing Noether KV to be wired up in every caloron deployment

A Noether-KV-backed variant is a swap-two-stages change if needed
later (replace `load_tick_state` + `save_tick_state` with stages that
shell out to Noether's KV stages).

## Configuration

```bash
export CALORON_KV_DIR=/var/lib/caloron/kv     # production override
# or accept the default ~/.caloron/kv/
```
