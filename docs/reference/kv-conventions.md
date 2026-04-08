# KV Store Conventions

All state lives in the Noether KV store (SQLite at `~/.noether/kv.db`). Keys use the `caloron:` prefix.

## Key Schema

| Key | Value | Updated by |
|-----|-------|------------|
| `caloron:{sprint_id}:state` | DagState JSON | dag_evaluate |
| `caloron:{sprint_id}:last_poll` | ISO timestamp | github_poll_events |
| `caloron:{sprint_id}:started_at` | ISO timestamp | kickoff |
| `caloron:{sprint_id}:agents` | Map of agent health | check_agent_health |
| `caloron:{sprint_id}:agent:{id}:pid` | Number (PID) | spawn_agent |
| `caloron:{sprint_id}:agent:{id}:last_heartbeat` | ISO timestamp | heartbeat handler |
| `caloron:{sprint_id}:interventions:{id}` | Number (count) | decide_intervention |
| `caloron:active_sprint` | `{ sprint_id, repo, stall_threshold_m }` | kickoff |

## Accessing from Stages

Use the Noether stdlib KV stages:

```bash
noether stage search "Store a JSON value under a key"
noether stage search "Retrieve a JSON value by key"
noether stage search "List all keys"
```

## Production Configuration

```bash
export NOETHER_KV_PATH=/var/lib/caloron/kv.db
```
