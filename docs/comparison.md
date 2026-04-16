# vs Original Caloron

Caloron-Noether is a reimplementation of [Caloron](https://github.com/alpibrusl/caloron). Same capabilities, different architecture.

## At a Glance

| | Caloron (Rust) | Caloron-Noether |
|---|---|---|
| **Total code** | ~9,300 lines Rust | ~28 stages (~2k Python) + 200-line Rust shell + Python orchestrator |
| **Business logic** | Rust modules | Python stages composed via Noether graphs (or driven directly by `orchestrator.py`) |
| **State** | In-memory + JSON files | Caloron KV directory (`~/.caloron/kv/`); orchestrator also uses a per-project workspace dir |
| **Orchestration** | Async Rust event loop | Two paths: production `caloron sprint` (Python orchestrator) and `noether-scheduler`-driven composition tick (newer, type-checks end-to-end; live pilot pending) |
| **Type checking** | Rust compiler | Noether graph type checker (compositions); runtime JSON checks (orchestrator) |
| **Caching** | Manual | Pure-stage output cache (Noether) |
| **Process mgmt** | Integrated in daemon | Separate shell (~200 LOC Rust) |
| **Agent harness** | Unix socket heartbeat | HTTP heartbeat |
| **Testing** | `cargo test` (192 tests) | `pytest` (269 tests, in-tree) + stub-framework integration harness |

## What Moved Where

| Original File | Lines | Replacement | Notes |
|--------------|-------|-------------|-------|
| `daemon/orchestrator.rs` | 404 | `orchestrator/orchestrator.py` (production) + `sprint_tick_stateful.json` (composition path) | Two implementations |
| `daemon/socket.rs` | 345 | `shell/heartbeat_server.rs` | HTTP instead of Unix socket |
| `daemon/state.rs` | 71 | Caloron KV (file-based) | One JSON per sprint |
| `git/monitor.rs` | 680 | `poll_events.py` + `evaluate.py` | Stages |
| `git/client.rs` | 237 | 6 GitHub/Gitea stages | `host` parameter targets either backend |
| `dag/engine.rs` | 627 | `evaluate.py` + 4 helper stages | Stages |
| `retro/` (5 files) | 2,083 | 4 retro stages | Now includes LLM-driven feedback analysis |
| `supervisor/` (4 files) | 934 | 3 supervisor stages | Stages |
| `kickoff/` (2 files) | 514 | 2 kickoff stages + 5 phase POs (architect/dev/review/design/flatten) | Phase pipeline is new |
| `agent/spawner.rs` | 336 | `shell/spawner.rs` | Rust |
| `main.rs` | 433 | `shell/main.rs` | Rust |

## What Did NOT Change

- **Agent harness** — same caloron-harness binary (heartbeat protocol changed from socket to HTTP)
- **Git protocol** — same labels, same feedback YAML format
- **DAG schema** — same structure, stored in KV instead of memory
- **Supervisor playbook** — same probe → restart → escalate ladder

## Trade-offs

### Caloron-Noether wins on

- **Code volume** — 6x less code
- **Composability** — stages are reusable across projects
- **Type checking** — graph-level type verification before execution
- **Caching** — Pure stages cached automatically
- **Debugging** — each stage testable in isolation (`echo | python3`)

### Original Caloron wins on

- **Type safety** — Rust compile-time guarantees vs runtime JSON
- **Single binary** — one `cargo build` vs Python + Nix + scheduler
- **Performance** — no Python subprocess overhead (though caching mitigates this)
- **IDE support** — Rust tooling (rust-analyzer) vs JSON composition graphs
- **Maturity** — 192 tests, full CLI, MkDocs documentation

## Verified Equivalence

The [comparison test](examples/comparison.md) runs the same diamond-dependency scenario through both and confirms identical state transitions, dependency resolution, and Gitea artifacts.
