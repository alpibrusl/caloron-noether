#!/usr/bin/env python3
"""CLI harness for running a Noether v0.3 stage as a subprocess.

Noether's v0.3 spec forbids ``sys.stdin`` / ``sys.stdout`` in stage
source files — the runner feeds input to ``execute()`` directly, and
stage code must return its output dict. See
``tests/test_stage_catalog.py:test_stage_sources_do_not_{read_stdin,
write_stdout}`` for the hard rule.

But CI jobs and humans sometimes want to test a single stage from the
shell with a JSON stdin → JSON stdout pipeline. This file is that
harness. It lives *outside* the stage catalogue (it's a shell utility,
not a Noether stage), so the "no stdin/stdout" rule doesn't apply.

Usage::

    echo '{"foo": 1}' | python3 stages/_run_stage.py stages/dag/evaluate.py

Exits non-zero with a human-readable stderr message on:

- missing stage file / invalid import
- invalid JSON on stdin
- missing ``execute`` symbol in the stage module
- ``execute`` raising an exception (traceback goes to stderr)

Does *not* participate in the stage catalogue, the registration
pipeline, or the Noether sprint-tick composition.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_execute(path: Path):
    if not path.is_file():
        sys.stderr.write(f"stage runner: file not found: {path}\n")
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("_stage_under_test", path)
    if spec is None or spec.loader is None:
        sys.stderr.write(f"stage runner: cannot load module: {path}\n")
        sys.exit(2)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pylint: disable=broad-except
        sys.stderr.write(f"stage runner: import failed for {path}: {exc}\n")
        sys.exit(2)
    execute = getattr(module, "execute", None)
    if not callable(execute):
        sys.stderr.write(
            f"stage runner: {path} has no callable `execute` symbol\n"
        )
        sys.exit(2)
    return execute


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(
            "usage: python3 stages/_run_stage.py <path/to/stage.py>\n"
        )
        return 2
    stage_path = Path(argv[1])
    execute = _load_execute(stage_path)

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"stage runner: invalid JSON on stdin: {exc}\n")
        return 2

    try:
        result = execute(payload)
    except Exception as exc:  # pylint: disable=broad-except
        sys.stderr.write(f"stage runner: execute() raised: {exc}\n")
        import traceback

        traceback.print_exc(file=sys.stderr)
        return 1

    json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
