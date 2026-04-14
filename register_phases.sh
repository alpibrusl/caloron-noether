#!/usr/bin/env bash
# Register the phase stages (architect_po → dev_po → review_po →
# phases_to_sprint_tasks) with a Noether v0.3+ store and emit a
# composition file with resolved stage hashes.
#
# Output: compositions/full_cycle_resolved.json — ready to run with
#   `noether run compositions/full_cycle_resolved.json --input '{...}'`
# and drop-in compatible with `caloron sprint --graph ...`.
#
# The legacy register_stages.sh targets noether v0.2 and is known stale
# for the rest of the stage catalogue. This script is self-contained
# and only covers the phases directory so you can get a working
# multi-role sprint graph without auditing every older stage.
#
# Requires: noether v0.3.0+, python3 on PATH.
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

specs = {
    "architect_po": {
        "description": "Architect PO — decompose a goal into components, design doc, and risks",
        "input":  {"Record": [["goal", "Text"], ["constraints", "Text"]]},
        "output": {"Record": [["design_doc", "Text"], ["components", {"List": "Any"}], ["risks", {"List": "Text"}]]},
    },
    "dev_po": {
        "description": "Dev PO — turn architect components into concrete agent tasks",
        "input":  {"Record": [["components", {"List": "Any"}], ["design_doc", "Text"], ["risks", {"List": "Text"}]]},
        "output": {"Record": [["design_doc", "Text"], ["components", {"List": "Any"}], ["risks", {"List": "Text"}], ["tasks", {"List": "Any"}]]},
    },
    "review_po": {
        "description": "Review PO — turn dev tasks into reviewer-assignable checks",
        "input":  {"Record": [["tasks", {"List": "Any"}], ["design_doc", "Text"]]},
        "output": {"Record": [["design_doc", "Text"], ["tasks", {"List": "Any"}], ["review_checks", {"List": "Any"}]]},
    },
    "phases_to_sprint_tasks": {
        "description": "Terminal flatten — merge phase outputs into single {tasks} list",
        "input":  {"Record": [["tasks", {"List": "Any"}], ["review_checks", {"List": "Any"}], ["design_doc", "Text"]]},
        "output": {"Record": [["tasks", {"List": "Any"}]]},
    },
}

ids = {}
for name, meta in specs.items():
    code_path = root / "stages" / "phases" / f"{name}.py"
    if not code_path.exists():
        print(f"missing stage source: {code_path}", file=sys.stderr)
        sys.exit(1)
    spec = {
        "name": name,
        "description": meta["description"],
        "input":  meta["input"],
        "output": meta["output"],
        "effects": [],
        "language": "python",
        "implementation": code_path.read_text(),
    }
    spec_path = Path(f"/tmp/caloron-phase-{name}.json")
    spec_path.write_text(json.dumps(spec))
    r = subprocess.run(
        [noether, "stage", "add", str(spec_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"stage add failed for {name}: {r.stderr or r.stdout}", file=sys.stderr)
        sys.exit(1)
    try:
        ids[name] = json.loads(r.stdout)["data"]["id"]
    except Exception:
        print(f"could not parse noether response for {name}: {r.stdout[:300]}", file=sys.stderr)
        sys.exit(1)
    print(f"  {name}: {ids[name][:16]}…")

graph = {
    "description": "caloron-noether full_cycle sprint graph (architect → dev → review → flatten)",
    "version": "0.1.0",
    "root": {
        "op": "Sequential",
        "stages": [
            {"op": "Stage", "id": ids["architect_po"]},
            {"op": "Stage", "id": ids["dev_po"]},
            {"op": "Stage", "id": ids["review_po"]},
            {"op": "Stage", "id": ids["phases_to_sprint_tasks"]},
        ],
    },
}
out = root / "compositions" / "full_cycle_resolved.json"
out.write_text(json.dumps(graph, indent=2) + "\n")
print(f"\nWrote {out}")
print(f"Run: {noether} run {out} --input '{{\"goal\": \"...\", \"constraints\": \"...\"}}'")
PY
