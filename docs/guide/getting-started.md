# Getting Started

## Prerequisites

- **Noether CLI** — built from [solv-noether](https://github.com/alpibrusl/solv-noether)
- **Python 3.11+** — for stage implementations
- **Rust 1.75+** — for the shell binary
- **Nix** (optional) — Noether uses it for hermetic stage execution
- **Docker** (optional) — for running Gitea locally

## Installation

```bash
# Clone
git clone https://github.com/alpibrusl/caloron-noether
cd caloron-noether

# Build the Noether CLI (if not already in PATH)
cd ../solv-noether
cargo build -p noether-cli
export PATH="$PWD/target/debug:$PATH"

# Verify
noether version
# → { "ok": true, "data": { "version": "0.1.0" } }

# Build the shell
cd ../caloron-noether
cargo build -p caloron-shell
```

## Register Stages

Custom stages must be registered in the Noether store before compositions can reference them:

```bash
./register_stages.sh
```

This registers all 16 stages and prints their hash IDs. Copy these into the composition graphs.

## Configuration

Set environment variables:

```bash
export GITHUB_TOKEN="ghp_..."          # or GITEA_TOKEN for local testing
export ANTHROPIC_API_KEY="sk-ant-..."  # for LLM stages (kickoff, retro)
export CALORON_SHELL_PORT=7710         # shell HTTP port (default: 7710)
```

## Run a Sprint

```bash
# 1. Start the shell (background)
./target/debug/caloron-shell &

# 2. Kickoff — generate DAG and create issues
noether run compositions/kickoff.json \
  --input '{"brief": "add user auth", "repo": "owner/repo", "num_agents": 2}'

# 3. Run sprint ticks manually (or use the scheduler)
noether run compositions/sprint_tick.json \
  --input '{"sprint_id": "sprint-1", "repo": "owner/repo", "stall_threshold_m": 20}'

# 4. Run retro when complete
noether run compositions/retro.json \
  --input '{"sprint_id": "sprint-1", "repo": "owner/repo"}'
```

## Automated Operation

For continuous operation, use `noether-scheduler`:

```bash
noether-scheduler --config scheduler.toml
```

This runs `sprint_tick.json` every 60 seconds until the sprint is complete.

## Testing Locally with Gitea

```bash
# Start Gitea
docker run -d --name gitea -p 3000:3000 gitea/gitea:1.22

# Run the comparison test
bash test/compare.sh
```
