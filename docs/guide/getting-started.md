# Getting Started

## Prerequisites

- **Python 3.11+** (stages run as Python scripts)
- **Rust 1.75+** (for the shell binary)
- **Noether CLI** — from [alpibrusl/noether](https://github.com/alpibrusl/noether)
- **Docker** (for Gitea, or use GitHub)
- **Claude Code** (Pro subscription or `ANTHROPIC_API_KEY`)

## Installation

```bash
git clone https://github.com/alpibrusl/caloron-noether
cd caloron-noether

# Build the Noether CLI
cd ../noether
cargo build --release -p noether-cli
export PATH="$PWD/target/release:$PATH"

# Build the shell
cd ../caloron-noether
cargo build -p caloron-shell

# Register custom stages
./register_stages.sh
```

## Run a Sprint

```bash
# Start Gitea
docker run -d --name gitea -p 3000:3000 gitea/gitea:1.22

# Run with noether backend
CALORON_BACKEND=noether python3 examples/orchestrator.py \
  "Build a Python module with is_palindrome function. Include tests."
```

## Deployment

For production, use Docker Compose or Kubernetes:

```bash
# Docker Compose (local/small team)
cd deploy/docker
docker compose up -d

# Kubernetes (enterprise)
cd deploy/k8s
helm install caloron .
```

See [Deployment Guide](../../deploy/README.md) for details.

## Next Steps

- [Architecture](architecture.md) — how stages, compositions, and the shell fit together
- [Stage Catalog](../reference/stage-catalog.md) — all 20 custom stages
- [vs Original Caloron](../comparison.md) — side-by-side comparison
