#!/usr/bin/env bash
# Register Caloron's legacy stage catalogue (DAG / GitHub / supervisor /
# retro / kickoff) with a Noether v0.3+ store.
#
# What this is: a thin driver that reads ``stage_catalog.py`` for the
# v0.3 spec shapes and inlines each stage's source from ``stages/**/*.py``
# at registration time. Closes caloron-noether issue #4 — the prior
# version of this file targeted Noether v0.2 and stopped working when
# the spec schema changed.
#
# Phase stages (architect_po, dev_po, review_po, phases_to_sprint_tasks)
# continue to be registered by ``register_phases.sh`` — keeping the two
# separate because the phase stages need the LLM helper inlined at
# registration time (see that script for details) while these don't.
#
# Usage:
#   ./register_stages.sh            # talk to local ~/.noether store
#   NOETHER_BIN=... ./register_stages.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
NOETHER="${NOETHER_BIN:-noether}"

python3 - "$ROOT" "$NOETHER" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
noether = sys.argv[2]

# Import the catalogue declared as data in stage_catalog.py.
sys.path.insert(0, str(root))
from stage_catalog import CATALOG  # noqa: E402

print(f"Registering {len(CATALOG)} legacy stages with {noether}…")
ids: dict[str, str] = {}
failures: list[tuple[str, str]] = []

for name, meta in CATALOG.items():
    code_path = root / meta["code_path"]
    if not code_path.exists():
        failures.append((name, f"missing source: {code_path}"))
        continue

    spec = {
        "name": name,
        "description": meta["description"],
        "input": meta["input"],
        "output": meta["output"],
        "effects": meta.get("effects", []),
        "language": "python",
        "implementation": code_path.read_text(),
    }
    spec_path = Path(f"/tmp/caloron-legacy-{name}.json")
    spec_path.write_text(json.dumps(spec))

    r = subprocess.run(
        [noether, "stage", "add", str(spec_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        failures.append(
            (name, (r.stderr or r.stdout).strip().splitlines()[-1][:200])
        )
        continue
    try:
        ids[name] = json.loads(r.stdout)["data"]["id"]
    except Exception as e:
        failures.append((name, f"unparseable response: {e}; out={r.stdout[:200]}"))
        continue
    print(f"  {name}: {ids[name][:16]}…")

if failures:
    print("\nFAILURES:", file=sys.stderr)
    for name, reason in failures:
        print(f"  {name}: {reason}", file=sys.stderr)
    sys.exit(1)

# Emit a resolved-id map so downstream compositions can reference the
# stages without pasting hashes everywhere.
out_map = root / "stage_ids.json"
out_map.write_text(json.dumps(ids, indent=2, sort_keys=True) + "\n")
print(f"\nWrote {out_map} with {len(ids)} resolved stage id(s).")
print("You can now `noether stage search <desc>` or reference them from compositions.")
PY
