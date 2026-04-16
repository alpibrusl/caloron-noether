# Caloron-Noether

**Multi-agent sprint orchestration. Two entry points: a Python orchestrator
(`caloron sprint`) for the runs people actually do today, and a set of
Noether composition graphs for the cron-driven path the platform is
moving towards.**

Caloron-Noether reimplements the [Caloron](https://github.com/alpibrusl/caloron)
orchestration platform with all sprint-internal business logic expressed
as [Noether](https://github.com/alpibrusl/noether) composition stages.
~200 lines of Rust manage agent processes; everything else is Python
stages or Python orchestration.

## What you can do today

| Path | Maturity | Use it for |
|------|----------|------------|
| `caloron sprint "<goal>"` (Python orchestrator) | **Production** | Real sprints — what every field user runs |
| `noether run compositions/full_cycle_resolved.json` (phase pipeline) | **Working** | Architect → dev → review → flatten as a Noether composition |
| `noether run compositions/sprint_tick_stateful.json` (per-tick loop) | **Type-checks; pilot pending** | Cron-driven scheduler ticks against Gitea or GitHub |

The Python orchestrator is what's been battle-tested across multiple
field sprints. The composition paths are how caloron is moving toward
a Noether-native, scheduler-driven runtime; v0.4.x got the wiring to
the point where they type-check end-to-end and individual stages run
correctly. End-to-end live validation against a real Gitea is the
remaining piece.

## Quick start

```bash
pip install caloron-alpibru        # the CLI
cargo install noether-cli          # only needed for the composition paths
```

Then either drive a real sprint via the CLI:

```bash
caloron init my-project --framework claude-code
caloron sprint "Build a Python module with is_palindrome. Include tests."
caloron status
```

Or run a phase composition through Noether:

```bash
./register_stages.sh        # registers ~28 caloron stages with the local Noether store
./register_phases.sh        # registers the architect/dev/review/flatten chain

noether run compositions/full_cycle_resolved.json --input \
  '{"goal": "Build a HealthCheck and a LoggingAdapter.", "constraints": ""}'
```

The `caloron sprint` path requires a running Gitea container — see
[Getting Started](guide/getting-started.md) for the full setup.

## Stage catalog (live count: ~28)

| Category | Examples | Effects |
|----------|----------|---------|
| **Phase POs** | `architect_po`, `dev_po`, `review_po`, `design_po`, `phases_to_sprint_tasks` | Llm, Pure |
| **Sprint glue** | `load_tick_state`, `save_tick_state`, `build_tick_output`, plus 3 reshape stages | Pure / Fallible |
| **DAG** | `dag_evaluate`, `dag_is_complete`, `dag_validate`, `unblocked_tasks`, `execute_actions` | Pure / Network |
| **GitHub / Gitea** | `github_poll_events`, `_create_issue`, `_post_comment`, `_add_label`, `_merge_pr`, `get_pr_status` | Network, Fallible |
| **Supervisor** | `check_agent_health`, `decide_intervention`, `compose_intervention_message` | Pure |
| **Retro** | `collect_sprint_feedback`, `compute_sprint_kpis`, `analyze_sprint_feedback`, `write_retro_report` | Pure / Llm / Network |
| **Kickoff** | `fetch_repo_context`, `generate_sprint_dag` | Network / Llm |

The github / kickoff stages take an optional `host` field — set to a
Gitea API root (e.g. `http://172.17.0.2:3000/api/v1`) to target a
self-hosted forge; defaults to `https://api.github.com`.

See [Stage Catalog](reference/stage-catalog.md) for full I/O signatures.

## Composition graphs

| Composition | Purpose |
|-------------|---------|
| `full_cycle.json` / `full_cycle_resolved.json` | The phase pipeline: `design_po → architect_po → dev_po → review_po → phases_to_sprint_tasks` — emits a typed task list ready for the orchestrator |
| `sprint_plan.json` | Architect + dev only (skips review). Lighter alternative for one-shot planning |
| `sprint_tick_core.json` | Pure per-tick loop: poll → evaluate → health → intervene → execute. Stateless; caller supplies state |
| `sprint_tick_stateful.json` | KV-wrapped variant: load state → run sprint_tick_core → save. What the scheduler is meant to call once live-piloted |
| `sprint_tick.json` | **Deprecated** — original v0.1 stub; kept for doc references only |

## CLI

```bash
caloron init <name> --framework claude-code
caloron sprint "<goal>" [--graph <composition>] [--po-timeout auto|<seconds>] [--debug]
caloron status
caloron history --limit 10
caloron show <sprint-id>
caloron metrics --output json
caloron agents
caloron projects {list, switch, delete}
caloron config get|set <key> [value]
caloron org {init, show, validate}    # organisation-wide conventions
```

All commands accept `--output text|json|table`. Conventions configured
via `caloron org init` are injected into every agent prompt — see the
[v0.3.2 changelog entry](https://github.com/alpibrusl/caloron-noether/blob/main/CHANGELOG.md)
for the schema.

## Where things live

```
caloron/                Python CLI package (caloron-alpibru on PyPI)
orchestrator/           Production sprint runner (orchestrator.py + helpers)
stages/                 Noether stage sources (~28 stages, hermetic Python)
  phases/               LLM-driven planning stages (architect/dev/review)
  sprint/               Sprint-tick reshape + KV stages
  dag/, github/, supervisor/, retro/, kickoff/   Domain stages
compositions/           Noether composition graphs (JSON)
shell/                  ~200-line Rust HTTP server (heartbeat + spawn)
scripts/                Sandbox scripts + stub_agent.py for testing
templates/              Project scaffolds (FastAPI, CLI, Next.js, Rust, etc.)
stage_catalog.py        v0.3 spec declarations for register_stages.sh
register_stages.sh      Registers domain stages with Noether
register_phases.sh      Registers phase + reshape stages
```
