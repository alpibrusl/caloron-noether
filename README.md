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

## Setup

```bash
# 1. Build Noether CLI
cd ../noether   # https://github.com/alpibrusl/noether && cargo build -p noether-cli
export PATH="$PWD/target/debug:$PATH"

# 2. Register custom stages
cd ../caloron-noether
./register_stages.sh

# 3. Build the shell
cargo build -p caloron-shell

# 4. Start the shell (heartbeat + spawn server)
CALORON_SHELL_PORT=7710 ./target/debug/caloron-shell

# 5. Start the scheduler (drives sprint ticks)
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

## Quick Sprint

```bash
# Run a full autonomous sprint
cd orchestrator
python3 orchestrator.py "Build a hotel rate anomaly detector with tests"
```

Supports 6 frameworks: `claude-code`, `cursor-cli`, `gemini-cli`, `codex-cli`, `open-code`, `aider`

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
