"""Shared pytest fixtures for caloron tests."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Import-time: `orchestrator.orchestrator` raises RuntimeError if
# GITEA_TOKEN is unset (see PR #24). Every test that imports the
# orchestrator — directly or transitively through caloron CLI commands —
# would fail collection without a value here. Inject a placeholder
# before any test collects; real tokens are only needed for live sprint
# runs, which don't exercise the test path.
#
# Tests that need to exercise the "unset GITEA_TOKEN" gate itself
# (tests/test_orchestrator_security.py) use monkeypatch.delenv in
# their own scope, which overrides this default.
os.environ.setdefault("GITEA_TOKEN", "fake-token-for-tests-only")


@pytest.fixture
def tmp_caloron_home(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolate ~/.caloron in a temp dir for the duration of the test."""
    tmp = Path(tempfile.mkdtemp(prefix="caloron-test-"))
    monkeypatch.setenv("CALORON_HOME", str(tmp))

    # Reload the project store module so it picks up the new env var
    import importlib

    import caloron.project.store as store_mod
    importlib.reload(store_mod)

    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        # Reset the module so other tests get a clean import
        importlib.reload(store_mod)
