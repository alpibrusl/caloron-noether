# Live Demo

Real recording of a Caloron-Noether sprint — not a simulation.

## Full Sprint: Charging Optimizer (Noether Backend)

PO Agent generates a DAG, agents build a charging window optimizer, Noether stages handle the retro analysis.

[![asciicast](https://asciinema.org/a/GOMIILJSz8ZpeF0R.svg)](https://asciinema.org/a/GOMIILJSz8ZpeF0R)

**What happens (5 minutes):**

1. **PO Agent** generates 2-task DAG (optimizer + tests)
2. **Agent 1** writes optimizer module (sandboxed)
3. **PR created on Gitea** → Reviewer: "APPROVED"
4. **PR merged** → Task 2 unblocked
5. **Agent 2** writes tests
6. **PR created** → Reviewer: "APPROVED" → **merged**
7. **Retro** via Noether stages — themes, improvements, sentiment analysis

Same sprint as [caloron](https://asciinema.org/a/ZsYVCt7uFAiTnEoP), different backend.

---

## Recording Your Own

```bash
asciinema rec my-demo.cast \
  -c "caloron sprint 'your goal here'"
```

(Pre-v0.2 docs referenced `examples/orchestrator.py`. That entry-point
moved into the `caloron` CLI as `caloron sprint`.)

## Also See

- [caloron demo](https://asciinema.org/a/ZsYVCt7uFAiTnEoP) — same sprint via direct Claude CLI
- [Comparison Test](examples/comparison.md) — side-by-side results
