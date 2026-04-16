# Stages

Every piece of business logic is a Noether stage — a typed Python
function that takes an input dict and returns an output dict. Noether
wraps it with type checking, effect tracking, and output caching.

## Stage contract

```python
"""<one-line description>.

Input:  { ...declared types... }
Output: { ...declared types... }

Effects: [Pure] / [Network, Fallible] / [Llm, NonDeterministic] / ...
"""

def execute(input: dict) -> dict:
    # ... logic ...
    return {...}
```

That's the whole contract. **Do not** read from `sys.stdin` or write to
`sys.stdout` — Noether's runner handles I/O for you. (Pre-v0.3.4 stages
did read stdin directly; that pattern was migrated out because Noether's
synthesised wrapper double-consumed the pipe. See the
v0.3.4 changelog for the full story.)

## Hermeticity

Stages run from `~/.noether/impl_cache/` with no access to the source
repo's layout. **No cross-module imports**: `from stages.phases._llm
import call_llm` works in unit tests but breaks at runtime. The
phase stages handle this by inlining their LLM helper at registration
time (see `register_phases.sh`'s `_inline_helper`).

## Effects

Declared per stage; Noether's type checker propagates them across
compositions. Common effect names (Noether v0.3.1+ accepts both bare
strings and capitalised forms):

- `Pure` — deterministic, cached by input hash
- `Fallible` — may raise
- `Network` — does I/O
- `Llm`, `NonDeterministic` — LLM call; not cached

Use `noether run --allow-effects pure,network` to gate which effects a
composition is allowed to perform.

## The catalog

See [Stage Catalog](../reference/stage-catalog.md) for the full list of
~28 stages with input/output signatures.

## Testing a stage in isolation

The simplest way is to import and call it:

```bash
python3 -c "
import sys; sys.path.insert(0, 'stages/dag')
from is_complete import execute
print(execute({'state': {'tasks': {'t1': {'status': 'Done'}}}}))
"
```

For stages that need a Noether-style harness (e.g. testing under
`noether run`), either register the stage with a fresh local store and
call `noether run` on a single-stage composition, or use the unit-test
patterns in `tests/test_*.py`.

## Adding a new stage

1. Drop the Python file under `stages/<category>/<name>.py` with the
   shape above.
2. Add an entry to `stage_catalog.py` declaring its input/output Record
   shape and effects.
3. Re-run `./register_stages.sh` to register it with Noether.
4. Add unit tests under `tests/`.
5. (Optional) Reference it from a composition graph by its hash.

`tests/test_stage_catalog.py` enforces three invariants automatically:
the catalog matches what's on disk, every stage exposes `execute()`,
and no stage reads stdin directly.
