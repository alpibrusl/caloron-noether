# Composition Graphs

JSON files that wire stages together. Noether type-checks the entire
graph before execution; you can dry-run any composition via
`noether run --dry-run <file>`.

## Graph format

```json
{
  "description": "What this composition does",
  "version": "0.1.0",
  "root": { "op": "Sequential", "stages": [ ... ] }
}
```

### Operators we use

| Op | Purpose |
|----|---------|
| `Stage` | Call a single stage by hash ID |
| `Sequential` | Pipe each stage's output into the next stage's input |
| `Let` | Run named bindings; the body sees the outer scope plus each binding's output as a nested field under the binding name |
| `Parallel` | Run branches concurrently; outputs nested under branch names |

We don't use `Branch`, `Fanout`, `Merge`, `Retry`, or `Const` in
caloron's compositions today — they're available if a future
composition needs them.

## Compositions in this repo

| File | Status | Purpose |
|------|--------|---------|
| `full_cycle.json` | Live | The phase pipeline: design → architect → dev → review → flatten. End-to-end planning. |
| `sprint_plan.json` | Live | Architect + dev only (no review). Lighter alternative for one-shot planning. |
| `sprint_tick_core.json` | Live | Pure per-tick loop, stateless |
| `sprint_tick_stateful.json` | Live | KV-wrapped sprint_tick_core: load state → tick → save |
| `kickoff.json` | Aspirational | One-shot DAG generation + Gitea issue creation |
| `retro.json` | Aspirational | Feedback collection + KPI computation + report |
| `spawn_agent.json` | Aspirational | Tiny wrapper around the shell's `/spawn` endpoint |
| `sprint_tick.json` | **Deprecated** | Original v0.1 stub; references stage IDs that haven't been valid since Noether v0.3 |

The aspirational ones are reference-quality JSON for what their
respective compositions could look like once register_stages.sh and the
relevant stages are wired up against your local Noether store.

## Resolved-ID files (gitignored)

`register_stages.sh` and `register_phases.sh` write
`compositions/full_cycle_resolved.json` and `stage_ids.json` (gitignored)
with the SHA-256 hashes Noether assigned at registration time. Other
compositions that want to reference these stages can either be
generated similarly or pull from `stage_ids.json`.

## Threading data through a Let chain — the key pattern

Each `Let` binding's output appears in the body's scope as a nested
field, not flattened. So if `poll: github_poll_events` outputs
`{events, polled_at}`, the body sees `{...outer, poll: {events,
polled_at}}`. The next stage that wants `events` at the top level
needs a tiny **reshape stage** to project it out:

```python
# stages/sprint/project_poll_to_eval.py
def execute(input):
    return {
        "state": input["state"],
        "events": input["poll"]["events"],
        "stall_threshold_m": input["stall_threshold_m"],
    }
```

This is what `stages/sprint/project_*.py` and the `build_tick_output`
stage do — small typed reshape stages between Let bindings and
Sequential steps. They keep each domain stage's input contract narrow
(no per-composition shape pollution) while making data flow explicit
in the graph itself.

We considered three alternatives — pass-through fields on every domain
stage, a generic untyped projection operator, and a monolithic
sprint_tick_core single stage — and rejected each for reasons recorded
in the v0.4.0 commit message.

## Type checking

```bash
noether run --dry-run compositions/full_cycle_resolved.json
```

The output's `type_check.input` field tells you the exact shape
the composition requires from its caller. Use this to design your
caller's input record before wiring anything up.
