# Scheduler Configuration

`noether-scheduler` drives the sprint loop. It replaces the hand-written `Orchestrator::run` async loop.

## Configuration

```toml
# scheduler.json

[[jobs]]
name        = "sprint-tick"
cron        = "* * * * *"                    # every minute
graph       = "./compositions/sprint_tick.json"
input_from  = "kv:caloron:active_sprint"     # reads sprint config from KV
on_error    = "log"                          # don't stop on single tick failure

[[jobs]]
name        = "retro"
cron        = "0 18 * * 5"                   # Fridays at 18:00
graph       = "./compositions/retro.json"
input_from  = "kv:caloron:active_sprint"
enabled     = false                          # enable at sprint close
```

## Running

```bash
noether-scheduler --config scheduler.json
```

## Manual Execution

Any composition can be run directly:

```bash
noether run compositions/sprint_tick.json \
  --input '{"sprint_id": "sprint-1", "repo": "owner/repo", "stall_threshold_m": 20}' \
  --allow-effects network,fallible,process
```
