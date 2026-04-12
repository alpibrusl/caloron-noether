"""Smoke tests for the caloron CLI.

These run the actual `caloron` command via subprocess to catch
regressions that would crash on `--help` or basic flows.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def cli_env(tmp_path: Path) -> dict[str, str]:
    """Env with isolated CALORON_HOME for CLI subprocess tests."""
    env = os.environ.copy()
    env["CALORON_HOME"] = str(tmp_path / ".caloron")
    return env


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "caloron.cli.main", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_help_does_not_crash(cli_env: dict[str, str]):
    result = _run(["--help"], cli_env)
    assert result.returncode == 0
    assert "caloron" in result.stdout.lower()


def test_version(cli_env: dict[str, str]):
    result = _run(["version"], cli_env)
    assert result.returncode == 0
    assert "caloron" in result.stdout
    assert "0.1.0" in result.stdout


def test_status_no_active_project(cli_env: dict[str, str]):
    result = _run(["status"], cli_env)
    assert result.returncode == 0
    assert "no active project" in result.stdout.lower()


def test_init_creates_project(cli_env: dict[str, str]):
    result = _run(["init", "smoke-test"], cli_env)
    assert result.returncode == 0
    assert "smoke-test" in result.stdout

    # Project state actually persisted
    home = Path(cli_env["CALORON_HOME"])
    assert (home / "projects" / "smoke-test" / "config.yml").exists()


def test_init_then_status(cli_env: dict[str, str]):
    _run(["init", "smoke-test"], cli_env)
    result = _run(["status"], cli_env)
    assert result.returncode == 0
    assert "smoke-test" in result.stdout


def test_init_then_list(cli_env: dict[str, str]):
    _run(["init", "p1"], cli_env)
    _run(["init", "p2"], cli_env)
    result = _run(["projects", "list"], cli_env)
    assert result.returncode == 0
    assert "p1" in result.stdout
    assert "p2" in result.stdout


def test_init_then_switch(cli_env: dict[str, str]):
    _run(["init", "p1"], cli_env)
    _run(["init", "p2"], cli_env)
    result = _run(["projects", "switch", "p2"], cli_env)
    assert result.returncode == 0
    status = _run(["status"], cli_env)
    assert "p2" in status.stdout


def test_metrics_empty(cli_env: dict[str, str]):
    _run(["init", "metric-test"], cli_env)
    result = _run(["metrics"], cli_env)
    assert result.returncode == 0
    assert "no sprints" in result.stdout.lower()


def test_introspect_returns_command_tree(cli_env: dict[str, str]):
    """ACLI introspect — agents discover capabilities at runtime."""
    result = _run(["introspect", "--output", "json"], cli_env)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["name"] == "caloron"
    cmd_names = {c["name"] for c in data["data"]["commands"]}
    # Sanity: all major commands discoverable
    for cmd in ("init", "sprint", "status", "history", "metrics", "agents"):
        assert cmd in cmd_names, f"Missing command in introspect: {cmd}"


def test_init_invalid_name_fails_cleanly(cli_env: dict[str, str]):
    result = _run(["init", "with/slash"], cli_env)
    assert result.returncode != 0
    # Should not be a stack trace
    assert "Traceback" not in result.stderr


def test_show_unknown_sprint_fails_cleanly(cli_env: dict[str, str]):
    _run(["init", "show-test"], cli_env)
    result = _run(["show", "999"], cli_env)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_status_json_envelope(cli_env: dict[str, str]):
    _run(["init", "json-test"], cli_env)
    result = _run(["status", "--output", "json"], cli_env)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["command"] == "status"
    assert data["data"]["project"] == "json-test"
    assert "duration_ms" in data["meta"]


def test_config_set_and_get(cli_env: dict[str, str]):
    _run(["init", "cfg-test"], cli_env)
    set_result = _run(["config", "set", "framework", "gemini-cli"], cli_env)
    assert set_result.returncode == 0
    get_result = _run(["config", "get", "framework"], cli_env)
    assert get_result.returncode == 0
    assert "gemini-cli" in get_result.stdout
