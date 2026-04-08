# The Shell

`caloron-shell` is the only Rust binary in the project. It handles two things that Noether composition graphs cannot do: managing OS processes and receiving HTTP heartbeats.

## Endpoints

### `POST /heartbeat`

Agents send heartbeats every 60 seconds.

```json
// Request
{ "agent_id": "agent-1", "sprint_id": "sprint-42", "status": "working" }

// Response
{ "ok": true }
```

Side effect: writes timestamp to KV at `caloron:{sprint_id}:agent:{agent_id}:last_heartbeat`.

### `POST /spawn`

Creates a git worktree and starts a harness process.

```json
// Request
{ "sprint_id": "sprint-42", "task_id": "task-1", "agent_id": "agent-1",
  "repo": "owner/repo", "worktree_base": ".caloron/worktrees" }

// Response
{ "ok": true, "pid": 12345 }
```

### `GET /status`

Lists all known agent processes and their liveness.

```json
// Response
{
  "agents": [
    { "agent_id": "agent-1", "sprint_id": "sprint-42",
      "pid": 12345, "alive": true, "last_heartbeat": "2026-04-08T12:00:00Z" }
  ]
}
```

### `GET /health`

Liveness probe. Returns `"ok"`.

## Running

```bash
CALORON_SHELL_PORT=7710 ./target/debug/caloron-shell
```

## Why Not Put This in a Stage?

Process spawning requires `fork`/`exec` and PID tracking. Noether stages are stateless functions — they can't hold a PID table across invocations. The shell is the minimal stateful component that the composition graphs call via HTTP.
