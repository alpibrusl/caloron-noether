# Scheduler Configuration

`noether-scheduler` (from the [Noether project](https://alpibrusl.github.io/noether/))
runs Lagrange graphs on a cron schedule. For caloron, the canonical
job is one tick of `sprint_tick_stateful.json` per minute.

> **Status note**: end-to-end live validation against a running Gitea
> via the scheduler hasn't been performed in our CI environment
> (sandbox can't reach the docker bridge). The composition type-checks
> and individual stages run correctly; live cron-driven sprint ticks
> are the next field-pilot opportunity.

## Configuration

`scheduler.json` (real, valid JSON — not TOML):

```json
{
  "store_path": ".noether/store.json",
  "jobs": [
    {
      "name": "sprint-tick",
      "cron": "* * * * *",
      "graph": "./compositions/sprint_tick_stateful.json",
      "input": {
        "sprint_id": "sprint-1",
        "repo": "caloron/full-loop",
        "stall_threshold_m": 20,
        "token_env": "GITEA_TOKEN",
        "shell_url": "http://localhost:7710",
        "host": "http://172.17.0.2:3000/api/v1"
      }
    }
  ]
}
```

`host` should be the Gitea container's bridge IP (find via
`docker network inspect bridge`); leave empty (`""`) to target
`api.github.com` instead.

## Running

```bash
GITEA_TOKEN=<your-gitea-token> noether-scheduler --config scheduler.json
```

The scheduler picks up changes to `scheduler.json` on next reload.
State persists between ticks under `$CALORON_KV_DIR`
(default `~/.caloron/kv/<sprint_id>.json`).

## Manual one-tick run (no cron)

```bash
noether run compositions/sprint_tick_stateful.json --input '{
  "sprint_id": "test",
  "repo": "caloron/full-loop",
  "stall_threshold_m": 20,
  "token_env": "GITEA_TOKEN",
  "shell_url": "http://localhost:7710",
  "host": "http://172.17.0.2:3000/api/v1"
}'
```

The composition's required input is exactly the 6 fields above.
Output is `{actions_taken, errors, persisted_path}`.

## Grid integration (Noether v0.4+)

When `noether-grid` is wired up across machines, set:

```json
{
  "store_path": ".noether/store.json",
  "grid_broker": "http://broker.internal:8088",
  "jobs": [ ... ]
}
```

The broker dispatches LLM-tagged stages across worker pool seats. See
the noether-grid docs for setup; caloron's stages declare effects so
the splitter routes them automatically. (Grid integration was piloted
locally; we identified bugs that the noether team fixed in v0.4.0,
but the cross-machine value-add hasn't been exercised against caloron
in production.)

## Older composition options

`compositions/sprint_tick_core.json` is the stateless variant — caller
supplies state directly each tick rather than reading it from disk. Use
this from a Python driver that manages persistence itself.

`compositions/sprint_tick.json` is the original v0.1 stub and is
deprecated; do not point the scheduler at it.
