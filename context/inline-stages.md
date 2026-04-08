# Inline Rust Stages — When and How to Promote

> Answer to the Caloron team's question: "under which criteria can we move Python/TypeScript
> stages into core?" and the follow-up: "how do we do it without coupling the projects?"

*April 2026 — applies to Noether ≥ 0.5.0 (commit `3b661ab`)*

---

## The short answer

You no longer need to modify `noether-core` to have compiled Rust stages.
`InlineRegistry` is a pluggable registry that lets `caloron-noether` ship its own
Rust stage implementations, loaded at executor startup, without touching Noether source.

---

## What changed in Noether

Previously, the only way to add a Rust stage implementation was to edit
`noether-engine/src/executor/stages/mod.rs` and add a line to the
`find_implementation` match table. That hard-coupled every project's stages into
Noether's binary.

As of `3b661ab`, Noether exposes:

```rust
// noether_engine::InlineRegistry
pub struct InlineRegistry { ... }

impl InlineRegistry {
    pub fn new() -> Self;
    pub fn register(&mut self, description: impl Into<String>, f: StageFn) -> &mut Self;
}

// Two new constructors on InlineExecutor and CompositeExecutor:
InlineExecutor::from_store_with_registry(store, registry)
CompositeExecutor::from_store_with_registry(store, registry)
```

Downstream crates now call `register` and pass the registry to the executor — no
Noether source modification needed.

---

## How to use it in caloron-noether

```rust
// caloron-noether/shell/src/executor_setup.rs

use noether_engine::InlineRegistry;
use noether_engine::executor::composite::CompositeExecutor;

fn my_dag_evaluate(input: &serde_json::Value)
    -> Result<serde_json::Value, noether_engine::executor::ExecutionError>
{
    // ... pure Rust logic ...
    Ok(output)
}

fn my_check_agent_health(input: &serde_json::Value)
    -> Result<serde_json::Value, noether_engine::executor::ExecutionError>
{
    // ... pure Rust logic ...
    Ok(output)
}

pub fn build_executor(store: &dyn noether_store::StageStore) -> CompositeExecutor {
    let mut registry = InlineRegistry::new();

    registry
        .register("Evaluate a sprint DAG from GitHub events", my_dag_evaluate)
        .register("Check agent health from heartbeat history", my_check_agent_health);

    CompositeExecutor::from_store_with_registry(store, registry)
}
```

The `description` string **must exactly match** the description you used when
registering the stage with `noether stage submit`. That is the key Noether uses to
route execution.

---

## The promotion criteria

Use this checklist before porting a Python stage to Rust:

```
□  Generality   — useful for ≥ 3 unrelated projects (not just Caloron)?
□  Hot path     — called > 1×/second AND 200ms startup visibly hurts latency?
□  Stable       — input/output schema unchanged for ≥ 1 sprint?
□  Worth it     — Rust impl is ≤ 2× the lines of the Python version?
```

**All four must be true.** A stage that passes only one or two checks should stay in Python.

### Applied to current Caloron stages

| Stage | Generality | Hot path | Stable | Port now? |
|---|---|---|---|---|
| `dag_evaluate` | ✗ Caloron-specific | ✗ 1×/60 s loop | Not yet | **No** |
| `check_agent_health` | ✓ Any polling system | ✗ 1×/60 s | Not yet | **No** |
| `decide_intervention` | ✗ Caloron-specific ladder | ✗ | Not yet | **No** |
| `compute_sprint_kpis` | ✓ Any sprint tool | ✗ | Close | **No yet** |
| `github_poll_events` | ✓ Any GitHub tool | ✗ | Close | **Candidate at v2** |
| LLM stages (retro, DAG gen) | ✗ Prompt is app-specific | ✗ | Never stable | **Always Python** |

**The honest answer for today: none of the Caloron stages should be ported yet.**
Build everything in Python first. The criteria enforce this.

---

## Why Python first is not a compromise

Two reasons it is actually the right call:

**1. Pure-stage output caching.**
Noether caches outputs of `Pure` stages by input hash. If `dag_evaluate` receives the
same `DagState` + same event list twice in a sprint tick, the second call costs ~0 ms
regardless of whether the stage is Rust or Python. Python startup overhead only occurs
on the first call per unique input.

**2. Interface stability.**
Stages are content-addressed. Every time you change the input or output type of a
registered stage, you get a new hash — and every composition graph that referenced the
old hash breaks. Porting to Rust before the interface is stable means you will port
twice. Build in Python, validate the schema across a sprint cycle, then port.

---

## The graduation path

When a stage finally meets all four criteria, the promotion path is:

```
1. Keep the Python stage registered and running in production.

2. Write the Rust fn (fn(&Value) -> Result<Value, ExecutionError>).

3. Test the Rust fn against the same input/output pairs as the Python stage.

4. Register in InlineRegistry with the SAME description string as the Python stage.
   The Rust fn will shadow the Python/Nix path — no graph changes needed.

5. Remove the Python stage from the NixExecutor store (optional cleanup).
```

Because `InlineRegistry` extras take priority over the NixExecutor (checked first
in `CompositeExecutor::execute`), swapping Python → Rust is a zero-downtime migration.

---

## What about TypeScript stages?

Same criteria and same path. TypeScript stages run through the same `NixExecutor`
as Python (spawns `nix run nixpkgs#nodejs -- script.ts`). If/when they meet the
promotion criteria, the `register` API is the same regardless of source language.

TypeScript may be preferred for:
- Stages that heavily manipulate JSON / DOM / HTML
- Stages where the team is more comfortable with TS than Python
- Stages that share types with the shell's frontend

All else is identical.

---

## Dependency

Add to `caloron-noether/shell/Cargo.toml`. Use path dependencies — no publishing
to crates.io needed, and `cargo build` always picks up the latest Noether changes
automatically:

```toml
[dependencies]
noether-engine = { path = "../../solv-noether/crates/noether-engine", features = ["native"] }
noether-core   = { path = "../../solv-noether/crates/noether-core" }
noether-store  = { path = "../../solv-noether/crates/noether-store" }
```

Then import:

```rust
use noether_engine::InlineRegistry;
use noether_engine::executor::composite::CompositeExecutor;
```

The `noether` CLI binary (for `noether stage search`, `noether run --dry-run`, etc.)
needs to be built once and kept in PATH:

```bash
cd /home/alpibru/workspace/solv-noether
cargo build --release -p noether-cli
export PATH="$PWD/target/release:$PATH"
```

Re-run that `cargo build` command whenever Noether changes — it takes ~10 s and
the binary is updated in place.
