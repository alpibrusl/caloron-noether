# Caloron-Noether

> **Reference application for [Noether](https://github.com/alpibrusl/noether).** Caloron-Noether is a working, non-trivial example of what Noether stages + the scheduler are good for. It runs sprint-style agent orchestration, but its real value is as documentation-by-example — "here is how you compose Noether stages into a real-world system."

If you want agent orchestration for your team, this repo works today, but the long-term focus is the primitives in Noether rather than features in Caloron. New ideas usually land as new *stages* (reusable across projects) rather than new orchestrator logic.

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

Caloron-Noether is a set of stages and compositions that run on top of [**Noether**](https://github.com/alpibrusl/noether) (v0.8.1+). You need both the `noether` CLI and `noether-scheduler` on your `PATH`.

```bash
cargo install noether-cli noether-scheduler
# or grab prebuilt binaries: https://github.com/alpibrusl/noether/releases/latest
```

See the [Noether docs](https://alpibrusl.github.io/noether/) for deeper configuration, and the [Scheduler guide](https://alpibrusl.github.io/noether/guides/scheduler/) for cron-driven compositions.

## Setup

```bash
# 1. Verify noether is installed (note: `noether version` is an ACLI subcommand, not `--version`)
noether version
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

All commands accept `--output text|json|table`. The framework selected at `caloron init --framework` is propagated to the PO, HR, and reviewer agents. Supported frameworks: `claude-code`, `cursor-cli`, `gemini-cli`, `codex-cli`, `open-code`, `aider`. Non-claude frameworks use their agentic / auto-approval mode (`-y` for Gemini, `--yes-always` for Aider, `exec --full-auto` for Codex, `-p` for cursor-agent); make sure the corresponding CLI is authenticated and on `$PATH`.

### Organisation conventions

Teams with a standard way of laying out projects, naming packages, or
licensing files can declare those rules once and have every caloron
sprint apply them. `caloron org init` scaffolds the file; edit it
with your conventions:

```bash
caloron org init              # writes ~/.caloron/organisation.yml
# edit ~/.caloron/organisation.yml
caloron org show              # preview the block every agent will see
caloron org validate          # sanity-check the YAML
```

Per-project overrides go in `<project>/caloron.yml` (right-wins merge).
Conventions are injected into the PO, agent, reviewer, and fix
prompts — they're not enforced at tool level (no ruff config
generation, no CI gate) today; the reviewer is the backstop.

### Runtime dependency — Gitea

Caloron uses Gitea as the version-control backend for sprints — issues,
PRs, merges, review comments all go through its API. A running Gitea
container is **required**; without it, `caloron sprint` aborts with
instructions. Start one with:

```bash
docker run -d --name gitea -p 3000:3000 -p 222:22 gitea/gitea:1.22
```

Set `GITEA_TOKEN` (or accept the dev-mode default) and configure your
project with `caloron config set repo <owner>/<repo>` pointing at a
repo you've created in that Gitea instance.

Bypass the preflight with `caloron sprint --skip-gitea-check` if you
intentionally want to run without version control (agent still runs;
all git/issue/PR calls become no-ops).

### Sandbox

On Linux, `caloron sprint` runs each agent inside a `bwrap` (bubblewrap) sandbox. On macOS and other systems where `bwrap` is unavailable, it falls back to a no-op passthrough script so `pip install caloron-alpibru` works out of the box. Override with `SANDBOX=/path/to/your-sandbox.sh` if you need custom isolation.

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
scripts/              Sandbox (bubblewrap on Linux, passthrough on macOS/other)
deploy/               Docker Compose + Kubernetes Helm chart
demo/                 Asciinema recording script
```

---

## Project status

**Reference app, not a supported product.** One active maintainer, best-effort response times. The stage catalogue and composition graphs are intentionally readable as a tutorial — if you're using caloron-noether to learn Noether, that's the primary use case. If you need agent orchestration for a team, it works today but don't deploy without reading [SECURITY.md](./SECURITY.md) and understanding the `CALORON_ALLOW_DANGEROUS_CLAUDE` gate (off by default — autonomous tool access requires explicit opt-in).

Not suitable for deployments requiring vendor SLAs.
