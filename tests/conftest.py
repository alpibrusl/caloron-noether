"""Shared pytest fixtures for caloron tests."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


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
