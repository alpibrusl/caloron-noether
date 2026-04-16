#!/usr/bin/env python3
"""Deterministic stub agent for caloron integration tests.

Replays a canned response from a JSON fixture file indicated by the
``CALORON_STUB_FIXTURE`` environment variable. Purpose: let
``tests/test_sprint_chain_integration.py`` and future full-loop
integration tests drive orchestrator.main() end-to-end without a live
LLM, a live Gitea, or any network dependency.

Fixture shape (JSON at ``$CALORON_STUB_FIXTURE``):

    {
        "responses": [
            {"match": "Product Owner", "output": "[{\"id\": ...}]"},
            {"match": "Reviewer", "output": "APPROVED"}
        ],
        "default": "stub: no matching response"
    }

On each invocation the script:
1. Reads the prompt (from ``--prompt`` argv or stdin).
2. Walks ``responses`` in order and returns the first ``output`` whose
   ``match`` substring is in the prompt.
3. Falls back to ``default`` if no response matches.

The fixture is replayed *statelessly* — every invocation starts over.
Tests that need sequential behaviour either use distinct ``match``
substrings per expected invocation, or maintain state externally
(a counter file the fixture reads, for example).

This script is not installed as part of the pip wheel; it lives under
``scripts/`` alongside the sandbox shell and is invoked by path via
the ``stub`` framework entry in ``orchestrator/orchestrator.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _load_fixture(path_str: str) -> dict:
    if not path_str:
        return {"responses": [], "default": "stub: no fixture set"}
    path = Path(path_str)
    if not path.is_file():
        return {"responses": [], "default": f"stub: fixture not found at {path}"}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as e:
        return {"responses": [], "default": f"stub: fixture parse error ({e})"}


def _response_for(prompt: str, fixture: dict) -> str:
    for entry in fixture.get("responses", []):
        match = entry.get("match", "")
        if match and match in prompt:
            return str(entry.get("output", ""))
    return str(fixture.get("default", "stub: no match and no default"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Caloron stub agent")
    parser.add_argument("--prompt", default="", help="Prompt text (or - for stdin)")
    parser.add_argument("positional", nargs="?", default="")
    args = parser.parse_args()

    prompt = args.prompt or args.positional
    if prompt == "-" or not prompt:
        prompt = sys.stdin.read()

    fixture = _load_fixture(os.environ.get("CALORON_STUB_FIXTURE", ""))
    sys.stdout.write(_response_for(prompt, fixture))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
