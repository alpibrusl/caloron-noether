# vs Original Caloron

Caloron-Noether is a reimplementation of [Caloron](https://github.com/alpibrusl/caloron). Same capabilities, different architecture.

## At a Glance

| | Caloron (Rust) | Caloron-Noether |
|---|---|---|
| **Total code** | ~9,300 lines Rust | ~1,200 lines (Python + Rust) |
| **Business logic** | Rust modules | Noether composition graphs |
| **State** | In-memory + JSON files | Noether KV store (SQLite) |
| **Orchestration** | Async Rust event loop | noether-scheduler (cron) |
| **Type checking** | Rust compiler | Noether graph type checker |
| **Caching** | Manual | Automatic (Pure stage cache) |
| **Process mgmt** | Integrated in daemon | Separate shell (~200 LOC) |
| **Agent harness** | Unix socket heartbeat | HTTP heartbeat |
| **Testing** | `cargo test` (192 tests) | `echo JSON \| python3` + Gitea e2e |

## What Moved Where

| Original File | Lines | Replacement | Lines |
|--------------|-------|-------------|-------|
| `daemon/orchestrator.rs` | 404 | `sprint_tick.json` + scheduler | 60 |
| `daemon/socket.rs` | 345 | `shell/heartbeat_server.rs` | 50 |
| `daemon/state.rs` | 71 | KV store (stdlib) | 0 |
| `git/monitor.rs` | 680 | `poll_events.py` + `evaluate.py` | 230 |
| `git/client.rs` | 237 | 5 GitHub stages | 250 |
| `dag/engine.rs` | 627 | `evaluate.py` | 130 |
| `retro/` (5 files) | 2,083 | 3 retro stages | 170 |
| `supervisor/` (4 files) | 934 | 3 supervisor stages | 140 |
| `kickoff/` (2 files) | 514 | 2 kickoff stages | 100 |
| `agent/spawner.rs` | 336 | `shell/spawner.rs` | 100 |
| `main.rs` | 433 | `shell/main.rs` | 80 |

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
