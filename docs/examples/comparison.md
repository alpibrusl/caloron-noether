# Comparison Test: Rust vs Python

The comparison test runs the same diamond-dependency DAG scenario through both implementations and verifies they produce identical results.

## The Scenario

3 tasks, diamond dependency:
```
task-1 (no deps)  ──┐
                     ├──→ task-3 (depends on both)
task-2 (no deps)  ──┘
```

## Run It

```bash
bash test/compare.sh
```

Requires: Gitea running in Docker, both repos created.

## Results

```
| Metric                | Rust (caloron)     | Python (caloron-noether) |
|-----------------------|--------------------|--------------------------|
| DAG engine lines      | 1011 lines         | 239 lines                |
| Execution time        | 777ms (incl build) | 917ms                    |
| State transitions     | Same               | Same                     |
| Dependency resolution | Same               | Same                     |
| Sprint completion     | true               | True                     |
| Gitea issues created  | 3                  | 3                        |
| Type safety           | Compile-time       | Runtime (JSON)           |
```

Both implementations:
- Unblock task-1 and task-2 (no deps) on init
- Keep task-3 Pending until both deps are Done
- Unblock task-3 only when task-1 AND task-2 are Done
- Report sprint complete when all 3 are Done
- Create 3 matching issues on Gitea
