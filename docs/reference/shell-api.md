# Shell HTTP API

The shell listens on `http://localhost:7710` (configurable via `CALORON_SHELL_PORT`).

## Endpoints

### `POST /heartbeat`

```bash
curl -X POST http://localhost:7710/heartbeat \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "agent-1", "sprint_id": "sprint-42", "status": "working"}'
```

Response: `{ "ok": true }`

### `POST /spawn`

```bash
curl -X POST http://localhost:7710/spawn \
  -H 'Content-Type: application/json' \
  -d '{
    "sprint_id": "sprint-42",
    "task_id": "task-1",
    "agent_id": "agent-1",
    "repo": "owner/repo",
    "worktree_base": ".caloron/worktrees"
  }'
```

Response: `{ "ok": true, "pid": 12345 }`

### `GET /status`

```bash
curl http://localhost:7710/status
```

Response:
```json
{
  "agents": [
    {
      "agent_id": "agent-1",
      "sprint_id": "sprint-42",
      "pid": 12345,
      "alive": true,
      "last_heartbeat": "2026-04-08T12:00:00Z"
    }
  ]
}
```

### `GET /health`

```bash
curl http://localhost:7710/health
```

Response: `ok`
