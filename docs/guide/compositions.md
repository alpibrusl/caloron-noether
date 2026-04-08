# Composition Graphs

Composition graphs are JSON files that wire stages together. Noether type-checks the entire graph before execution.

## Graph Format

```json
{
  "description": "What this composition does",
  "version": "0.1.0",
  "root": { "op": "Sequential", "stages": [ ... ] }
}
```

### Node Types

| Op | Description |
|----|-------------|
| `Stage` | Call a single stage by hash ID |
| `Sequential` | Pipe output of each stage to the next |
| `Parallel` | Run branches concurrently, merge outputs |
| `Branch` | Conditional: if/then/else |

## `sprint_tick.json`

The main loop. Run every 60 seconds by the scheduler.

```
Input:  { sprint_id, repo, stall_threshold_m }
Output: { actions_taken, dag_complete }

Flow:
1. Parallel: load DagState + last_poll + agents from KV
2. Poll GitHub events
3. Save last_poll
4. Evaluate DAG → produce actions
5. Save DagState
6. Parallel: health checks + completion check
7. Execute actions (spawn, merge, comment, escalate)
```

## `kickoff.json`

One-shot. Generates a DAG and creates GitHub issues.

```
Input:  { brief, repo, num_agents }
Output: { sprint_id, dag, issues_created }

Flow:
1. Fetch repo context
2. Generate DAG from brief
3. Validate DAG
4. Save to KV
5. Create issues
```

## `retro.json`

One-shot. Collects feedback and generates a report.

```
Input:  { sprint_id, repo }
Output: { report_path }

Flow:
1. Load final DagState from KV
2. Parallel: collect feedback + compute KPIs
3. Write report
```

## `spawn_agent.json`

Called by the sprint tick when a task is ready.

```
Input:  { sprint_id, task_id, agent_id, repo, worktree_base }
Output: { pid, started_at }

Flow:
1. POST to caloron-shell /spawn
2. Save PID to KV
```

## Type Checking

Validate a graph without executing:

```bash
noether run --dry-run compositions/sprint_tick.json \
  --input '{"sprint_id": "x", "repo": "o/r", "stall_threshold_m": 20}'
```

This catches type mismatches between stages before any side effects occur.
