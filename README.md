# Caloron-Noether

> **Reference application for [Noether](https://github.com/alpibrusl/noether).**
> Sprint-style multi-agent orchestration written as Noether composition
> graphs. The codebase is meant to be read as documentation-by-example —
> "here is how you compose Noether stages into a real-world system."

## Status

One active maintainer. **Reference app, not a supported product** —
best-effort response times, no SLAs. New ideas usually land as new
*stages* in [Noether](https://github.com/alpibrusl/noether) (reusable
across projects) rather than orchestrator features here.

- Trust model: [`SECURITY.md`](./SECURITY.md)
- Release notes: [`CHANGELOG.md`](./CHANGELOG.md)
- Walk-through: [`docs/tutorial/index.md`](./docs/tutorial/index.md) — evolve `citecheck` with an autonomous sprint
- Roadmap notes: [`docs/roadmap/`](./docs/roadmap/)

## Architecture

```
noether-scheduler (cron: sprint_tick.json every 60s)
        │
        ▼
Noether engine (runs composition graphs)
  ├── DAG stages         — evaluate, is_complete, validate
  ├── GitHub stages      — poll, create_issue, comment, merge
  ├── Supervisor stages  — health checks, interventions, messaging
  ├── Retro stages       — feedback, KPIs, report
  └── Kickoff stages     — repo context, DAG generation
        │
        ▼
caloron-shell (~200 lines Rust, axum)
  ├── POST /spawn      — create worktree + start agent harness
  ├── POST /heartbeat  — record agent heartbeats
  └── GET  /status     — list live agents
```

All business logic lives in Noether stages (Python). The Rust shell
only manages processes and HTTP.

## Install

```bash
pip install caloron-alpibru                   # Python CLI + Noether stages
cargo install noether-cli noether-scheduler   # Noether runtime (v0.8.1+)
cargo build -p caloron-shell                  # the HTTP shell
```

Optional runtime dependencies:

- **Gitea** — required for the sprint backend (issues, PRs, merges go
  through its API). `docker run -d -p 3000:3000 gitea/gitea:1.22`.
  Bypass with `caloron sprint --skip-gitea-check` for a no-op git/PR
  loop.
- **bubblewrap** — Linux sandbox for spawned agents. Falls back to a
  passthrough script on macOS / non-Linux. Override with `SANDBOX=...`.
- **`llm-here`** — required for `call_llm` to dispatch to a provider.
  `cargo install llm-here`. Without it, LLM-shaped stages return
  `None` and callers fall back to deterministic templates.

## Usage

```bash
# 1. Verify noether is installed (note: ACLI subcommand, not --version)
noether version
noether-scheduler --version

# 2. Start the shell + scheduler (two terminals or via systemd)
CALORON_SHELL_PORT=7710 ./target/debug/caloron-shell
noether-scheduler --config scheduler.json

# 3. Drive sprints from the CLI
caloron init my-project --backend noether
caloron sprint "Build a hotel rate anomaly detector"
caloron status                  # active project + last sprint
caloron history --limit 10      # past sprints
caloron show 5                  # full retro for sprint #5
caloron metrics --output json   # aggregated KPIs
caloron agents                  # agent profiles in this project
```

All commands accept `--output text|json|table`. Agent frameworks
(settable via `caloron init --framework` or `caloron config set
framework`): `claude-code`, `cursor-cli`, `gemini-cli`, `codex-cli`,
`open-code`, `aider`. Each must be authenticated and on `$PATH`;
non-claude frameworks use their agentic / auto-approval mode.

`caloron org init` scaffolds an organisation-conventions file
(`~/.caloron/organisation.yml`) injected into every PO / agent /
reviewer prompt. Per-project overrides go in `<project>/caloron.yml`
(right-wins merge).

## When Caloron-Noether is *not* the right tool

- **Production agent orchestration with SLAs** — this is a reference
  app. Deploy it to learn from it, not to bet a product on it.
- **Hardened multi-tenant sandbox** — bwrap is sized for "LLM agents I
  haven't audited", not "adversaries targeting a shared kernel". See
  [`SECURITY.md`](./SECURITY.md).
- **Closed-source / private LLM-only flows** — caloron's prompts go
  through `llm-here`; if that doesn't reach your provider, the
  caller-side `None` fallback is the contract, not silent retry.
- **Autonomous tool access on by default** —
  `CALORON_ALLOW_DANGEROUS_CLAUDE` is opt-in per the SECURITY.md
  threat model. If your workflow needs `claude --dangerously-skip-permissions`
  always-on, you'll be flipping a flag every sprint.

## Project structure

```
orchestrator/   Sprint runtime (Python) — main loop, HR / PO / supervisor / agentspec bridge
stages/         Noether Python stages (stdin JSON → stdout JSON)
compositions/   Noether composition graphs (JSON)
shell/          Rust binary (axum HTTP server)
caloron/        ACLI-compliant CLI surface (Python)
templates/      Project scaffolds (fastapi, fastapi-postgres, python-data, nextjs, rust-cli)
deploy/         Docker Compose + Helm chart
scripts/        bubblewrap and passthrough sandbox scripts
docs/tutorial/  Reference walk-through: evolve citecheck with an autonomous sprint
docs/roadmap/   Roadmap notes (per-date)
```

## License

EUPL-1.2 — see [`LICENSE`](./LICENSE).
