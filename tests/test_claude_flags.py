"""Tests for orchestrator.claude_flags — dangerous-permissions opt-in gate."""

from __future__ import annotations

import pytest
from orchestrator.claude_flags import (
    ENV_VAR,
    dangerous_enabled,
    dangerous_flags,
)


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    return monkeypatch


def test_disabled_by_default(clean_env):
    assert dangerous_enabled() is False
    assert dangerous_flags() == []


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "Yes", "  on  "])
def test_enabled_by_truthy(clean_env, val):
    clean_env.setenv(ENV_VAR, val)
    assert dangerous_enabled() is True
    assert dangerous_flags() == ["--dangerously-skip-permissions"]


@pytest.mark.parametrize("val", ["", "0", "false", "no", "off", "maybe", "FALSE"])
def test_falsy_stays_disabled(clean_env, val):
    clean_env.setenv(ENV_VAR, val)
    assert dangerous_enabled() is False
    assert dangerous_flags() == []


# NOTE: integration tests for build_agent_command live in test_framework_dispatch
# (when that module imports orchestrator via the project's runtime import path).
# Keeping this module to unit tests of the helper itself.
