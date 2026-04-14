# Getting Started

## Prerequisites

- **Python 3.11+** (stages run as Python scripts)
- **Rust 1.75+** (for the shell binary)
- **Noether v0.3.0+** — `noether` CLI and `noether-scheduler` on `PATH`. See the [Noether docs](https://alpibrusl.github.io/noether/).
- **Docker** (for Gitea, or use GitHub)
- **Claude Code** (Pro subscription or `ANTHROPIC_API_KEY`)

## Installation

```bash
git clone https://github.com/alpibrusl/caloron-noether
cd caloron-noether

# Install Noether (CLI + scheduler)
cargo install noether-cli noether-scheduler
# or download prebuilt binaries from
#   https://github.com/alpibrusl/noether/releases/latest

# (Optional) point at the hosted stage registry
export NOETHER_REGISTRY=https://registry.alpibru.com

# Build the shell
cargo build -p caloron-shell

# Register custom stages
./register_stages.sh

# Install the caloron CLI
pip install -e .
```

## Run a Sprint

The recommended path is the `caloron` CLI:

```bash
caloron init my-project --backend noether
caloron sprint "Build a Python module with is_palindrome function. Include tests."
caloron status
```

Or call the underlying orchestrator directly:

```bash
docker run -d --name gitea -p 3000:3000 gitea/gitea:1.22

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
