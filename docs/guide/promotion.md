# Stage Promotion: Python → Rust

All stages start as Python. When they mature, they can be promoted to compiled Rust for faster execution — with zero changes to composition graphs.

## Promotion Criteria

All four must be true:

| Criterion | Question |
|-----------|----------|
| **Generality** | Useful for 3+ unrelated projects? |
| **Hot path** | Called >1x/second AND 200ms startup hurts? |
| **Stable** | Input/output schema unchanged for 1+ sprint? |
| **Worth it** | Rust impl is ≤2x the lines of Python? |

## Current Stage Assessment

| Stage | General | Hot | Stable | Promote? |
|-------|---------|-----|--------|----------|
| dag_evaluate | No (Caloron-specific) | No (1x/60s) | Not yet | **No** |
| check_agent_health | Yes (any poller) | No | Not yet | **No** |
| compute_kpis | Yes (any sprint) | No | Close | **Not yet** |
| github_poll_events | Yes (any GitHub tool) | No | Close | **Candidate v2** |
| LLM stages | No (prompt is app-specific) | No | Never | **Always Python** |

**Honest answer: none should be promoted yet.** Build in Python, validate schemas, then port.

## How It Works

Noether 0.5+ provides `InlineRegistry`:

```rust
use noether_engine::InlineRegistry;

fn my_dag_evaluate(input: &serde_json::Value)
    -> Result<serde_json::Value, ExecutionError>
{
    // Rust implementation
    Ok(output)
}

let mut registry = InlineRegistry::new();
registry.register("Evaluate a sprint DAG from GitHub events", my_dag_evaluate);

let executor = CompositeExecutor::from_store_with_registry(store, registry);
```

The description string must **exactly match** the registered stage description. The Rust function shadows the Python/Nix path — no graph changes needed.

## Why Python First Is Not a Compromise

1. **Pure-stage caching** — Noether caches Pure stage outputs by input hash. Second call costs ~0ms regardless of language.
2. **Interface stability** — Stages are content-addressed. Changing the schema creates a new hash, breaking all graph references. Port after the schema is stable, not before.
