# Caloron-Noether

Caloron reimplemented as Noether composition graphs. Same orchestration capabilities, ~6x less code.

## Architecture

```
noether-scheduler (cron: sprint_tick.json every 60s)
        │
        ▼
Noether Engine (runs composition graphs)
  ├── DAG stages (Pure Python) — evaluate, is_complete, validate
  ├── GitHub stages (Network Python) — poll, create_issue, comment, merge
  ├── Supervisor stages (Pure Python) — health check, intervention, messaging
  ├── Retro stages (Pure/Network Python) — feedback, KPIs, report
  └── Kickoff stages (Network/LLM Python) — repo context, DAG generation
        │
        ▼
caloron-shell (~200 lines Rust, axum)
  ├── POST /heartbeat — record agent heartbeats
  ├── POST /spawn — create worktree + start harness
  └── GET /status — list live agents
```

All business logic is in Noether stages (Python). The shell only manages processes and HTTP.

## Prerequisites

Caloron-Noether is a set of stages and compositions that run on top of [**Noether**](https://github.com/alpibrusl/noether) (v0.3.0+). You need both the `noether` CLI and `noether-scheduler` on your `PATH`.

```bash
cargo install noether-cli noether-scheduler
# or grab prebuilt binaries: https://github.com/alpibrusl/noether/releases/latest
```

See the [Noether docs](https://alpibrusl.github.io/noether/) for deeper configuration, and the [Scheduler guide](https://alpibrusl.github.io/noether/guides/scheduler/) for cron-driven compositions.

## Setup

```bash
# 1. Verify noether is installed
noether --version
noether-scheduler --version

# 2. (Optional) Point at the hosted stage registry
export NOETHER_REGISTRY=https://registry.alpibru.com

# 3. Register custom stages
./register_stages.sh

# 4. Build the shell
cargo build -p caloron-shell

# 5. Start the shell (heartbeat + spawn server)
CALORON_SHELL_PORT=7710 ./target/debug/caloron-shell

# 6. Start the scheduler (drives sprint ticks + weekly retro)
noether-scheduler --config scheduler.json
```

## Documentation

Full docs: [docs/](docs/) — build locally with `mkdocs serve`.

- [Getting Started](docs/guide/getting-started.md)
- [Architecture](docs/guide/architecture.md)
- [Stage Catalog](docs/reference/stage-catalog.md)
- [Composition Graphs](docs/guide/compositions.md)
- [Shell API](docs/reference/shell-api.md)
- [KV Conventions](docs/reference/kv-conventions.md)
- [vs Original Caloron](docs/comparison.md)
- [Deployment (Docker + K8s)](deploy/README.md)

## Stage Promotion Path

All stages start as Python. When a stage meets all four criteria (generality, hot path, stable schema, worth the lines), it can be promoted to Rust via `InlineRegistry` — zero graph changes needed. See `context/inline-stages.md`.

## CLI

Installing the package (`pip install caloron-noether`) exposes a `caloron` ACLI-compliant command:

```bash
caloron init my-project --backend noether            # create a project
caloron sprint "Build a hotel rate anomaly detector" # run an autonomous sprint
caloron status                                       # active project + last sprint
caloron history --limit 10                           # past sprints
caloron show 5                                       # full retro for sprint #5
caloron metrics --output json                        # aggregated KPIs
caloron agents                                       # agent profiles in this project
caloron projects list | switch | delete              # multi-project management
caloron config get|set <key> [value]                 # per-project settings
```

All commands accept `--output text|json|table`. Supports 6 agent frameworks: `claude-code`, `cursor-cli`, `gemini-cli`, `codex-cli`, `open-code`, `aider`.

## Project Structure

```
orchestrator/         Sprint runtime (Python)
  orchestrator.py     Main loop: PO → agents → PRs → reviews → retro
  skill_store.py      Registry of skills/MCPs (18 built-in, user-extensible)
  hr_agent.py         Assigns skills + model + framework per task
  agent_configurator.py  Writes CLAUDE.md/.cursorrules/GEMINI.md + MCP configs
  agent_versioning.py    Tracks agent evolution across sprints
  template_store.py      Project scaffolds (YAML templates + LLM generation)
templates/            Project templates (user-extensible YAML)
  fastapi.yaml        FastAPI + ruff + pytest + Dockerfile
  fastapi-postgres.yaml  + SQLAlchemy + Alembic + docker-compose
  python-data.yaml    pandas + data dir + fixtures
  nextjs.yaml         Next.js 14 + TypeScript + Tailwind
  rust-cli.yaml       clap + clippy + fmt CI
stages/               Noether Python stages (stdin JSON → stdout JSON)
  dag/                DAG evaluation, completion, validation
  github/             GitHub/Gitea API operations
  supervisor/         Health checks, interventions, messaging
  retro/              Feedback, KPIs, report generation
  kickoff/            Repo context, DAG generation
compositions/         Noether composition graphs (JSON)
shell/                Thin Rust binary (axum HTTP server)
scripts/              Sandbox (bubblewrap)
deploy/               Docker Compose + Kubernetes Helm chart
demo/                 Asciinema recording script
```
