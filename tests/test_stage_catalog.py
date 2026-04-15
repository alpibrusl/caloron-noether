"""Sanity tests for the legacy stage catalogue.

Stops three classes of regression:

1. Stage catalogue drifting out of sync with stage source files — every
   declared entry must have a file on disk.
2. Source files losing the ``execute(input)`` entry point — Noether v0.3
   expects it, so if someone "fixes" a stage and inlines the stdin/out
   code again, this fires.
3. v0.3 spec shape drift — if someone adds an entry with the old v0.2
   schema it won't register; this catches it at unit-test time instead
   of at sprint-tick time.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from stage_catalog import CATALOG  # noqa: E402, I001


# ── Catalogue shape ────────────────────────────────────────────────────────


def test_catalog_is_non_empty():
    assert len(CATALOG) >= 15, "legacy catalogue unexpectedly shrunk"


def test_every_entry_has_required_fields():
    required = {"code_path", "description", "input", "output", "effects"}
    for name, meta in CATALOG.items():
        missing = required - meta.keys()
        assert not missing, f"{name} missing {missing}"


def test_input_output_are_v03_record_shape():
    """Record schemas use the ``[[key, type], ...]`` tuple list, not the
    v0.2 ``{type: Record, fields: {...}}`` dict."""
    for name, meta in CATALOG.items():
        for direction in ("input", "output"):
            spec = meta[direction]
            assert isinstance(spec, dict), f"{name}.{direction}: not a dict"
            assert "Record" in spec, f"{name}.{direction}: missing Record"
            fields = spec["Record"]
            assert isinstance(fields, list), (
                f"{name}.{direction}: Record should be a list of tuples, got {type(fields).__name__}"
            )
            for field_entry in fields:
                assert isinstance(field_entry, list) and len(field_entry) == 2, (
                    f"{name}.{direction}: each field must be [key, type], got {field_entry!r}"
                )


def test_effects_are_plain_string_list():
    """v0.3 accepts bare strings. The v0.2 ``[{"effect": "Pure"}]`` wrapper
    no longer matches the stage-spec schema — guard against re-introducing."""
    for name, meta in CATALOG.items():
        effects = meta["effects"]
        assert isinstance(effects, list), f"{name}: effects not a list"
        for e in effects:
            assert isinstance(e, str), (
                f"{name}: effect {e!r} is not a bare string — v0.2 style rejected by noether v0.3"
            )


# ── Source files on disk ────────────────────────────────────────────────────


@pytest.mark.parametrize("name,meta", sorted(CATALOG.items()))
def test_each_stage_has_source_on_disk(name: str, meta: dict):
    path = _REPO_ROOT / meta["code_path"]
    assert path.is_file(), f"{name}: {meta['code_path']} not found"


@pytest.mark.parametrize("name,meta", sorted(CATALOG.items()))
def test_each_stage_exposes_execute(name: str, meta: dict):
    """Stage files must define ``execute`` at module level."""
    path = _REPO_ROOT / meta["code_path"]
    tree = ast.parse(path.read_text())
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert "execute" in names, (
        f"{name}: {meta['code_path']} has no top-level `execute` function"
    )


@pytest.mark.parametrize("name,meta", sorted(CATALOG.items()))
def test_stage_sources_do_not_read_stdin(name: str, meta: dict):
    """v0.3 runner passes input via synthesised preamble — user code that
    reads stdin double-consumes the pipe and breaks (see the v0.3.0
    register_phases.sh fix for the full story)."""
    path = _REPO_ROOT / meta["code_path"]
    src = path.read_text()
    assert "sys.stdin" not in src, (
        f"{name}: uses sys.stdin at module level — migrate to execute(input)"
    )


@pytest.mark.parametrize("name,meta", sorted(CATALOG.items()))
def test_stage_sources_do_not_write_stdout(name: str, meta: dict):
    """Same issue in the other direction: stage body must return its
    output dict, not print it — the runner does its own serialisation."""
    path = _REPO_ROOT / meta["code_path"]
    src = path.read_text()
    assert "sys.stdout" not in src, (
        f"{name}: writes to sys.stdout — use `return {{...}}` from execute instead"
    )
