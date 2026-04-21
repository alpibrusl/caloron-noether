"""Smoke tests for the caloron CLI.

These run the actual `caloron` command via subprocess to catch
regressions that would crash on `--help` or basic flows.

## Running locally

These tests import-check against `caloron.cli.main`, which depends on
`typer`. If you're seeing 19 skipped tests on your machine, run:

    pip install -e '.[dev]'

from the repo root. CI runs this in the `Caloron CLI Tests` workflow
job and the suite passes there — cf. PR #20 / PR #26 for the history
of this footgun.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Early-skip with a diagnostic message if the CLI's runtime deps are
# missing, rather than letting 19 individual tests fail with the same
# unhelpful `ModuleNotFoundError`. See the module docstring for the
# fix (pip install the package with dev extras).
try:
    from caloron.cli import main as _cli_import_probe  # noqa: F401 — side-effecting import check
except ModuleNotFoundError as _exc:
    pytest.skip(
        f"caloron.cli is not importable ({_exc}). "
        "Run `pip install -e .[dev]` from the repo root to install the "
        "runtime + test dependencies; CI does this automatically. See "
        "the module docstring for the full context.",
        allow_module_level=True,
    )


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
    assert "0.4.2" in result.stdout


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


def test_sprint_graph_missing_file(cli_env: dict[str, str]):
    _run(["init", "graph-test"], cli_env)
    result = _run(["sprint", "demo", "--graph", "/nonexistent/plan.json"], cli_env)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    # Error should mention the graph file, not explode on the orchestrator
    combined = (result.stdout + result.stderr).lower()
    assert "graph" in combined or "not found" in combined


def test_sprint_graph_without_noether_cli(cli_env: dict[str, str], tmp_path: Path):
    """--graph with a valid file but no noether binary should fail cleanly."""
    _run(["init", "graph-test"], cli_env)

    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"description": "stub", "root": {"op": "Const", "value": {}}}))

    # Scrub PATH so `noether` can't be found, but keep python + basic utils
    # by pointing at a directory that only has python/coreutils.
    env_no_noether = cli_env.copy()
    env_no_noether["PATH"] = "/usr/bin:/bin"
    # Confirm noether isn't in that PATH — if the test host has it globally
    # under /usr/bin this assertion saves us from a false pass.
    if shutil_which_in_path("noether", env_no_noether["PATH"]):
        pytest.skip("noether present on /usr/bin, cannot exercise missing-CLI path")

    result = _run(["sprint", "demo", "--graph", str(plan)], env_no_noether)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    combined = (result.stdout + result.stderr).lower()
    assert "noether" in combined


def shutil_which_in_path(cmd: str, path: str) -> str | None:
    """Lightweight `which` scoped to an explicit PATH."""
    for d in path.split(os.pathsep):
        candidate = Path(d) / cmd
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def test_org_show_empty_by_default(cli_env: dict[str, str]):
    """Fresh CALORON_HOME has no conventions → helpful empty message."""
    result = _run(["org", "show"], cli_env)
    assert result.returncode == 0
    assert "no conventions configured" in result.stdout.lower()


def test_org_init_creates_template(cli_env: dict[str, str]):
    result = _run(["org", "init"], cli_env)
    assert result.returncode == 0
    home = Path(cli_env["CALORON_HOME"])
    assert (home / "organisation.yml").is_file()
    # Re-running complains instead of overwriting.
    result2 = _run(["org", "init"], cli_env)
    assert result2.returncode != 0
    assert "already exists" in (result2.stdout + result2.stderr).lower()


def test_org_show_renders_conventions_after_edit(cli_env: dict[str, str]):
    """Init → edit the file → `org show` renders the configured rules."""
    _run(["org", "init"], cli_env)
    home = Path(cli_env["CALORON_HOME"])
    org_file = home / "organisation.yml"
    org_file.write_text(
        'organisation: "Acme Corp"\n'
        "package_naming:\n  style: kebab-case\n  prefix: acme-\n"
    )
    result = _run(["org", "show"], cli_env)
    assert result.returncode == 0
    assert "Acme Corp" in result.stdout
    assert "kebab-case" in result.stdout
    assert "acme-" in result.stdout


def test_org_validate_flags_malformed_yaml(cli_env: dict[str, str]):
    home = Path(cli_env["CALORON_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    (home / "organisation.yml").write_text("not: valid: yaml: [")
    result = _run(["org", "validate"], cli_env)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_config_set_and_get(cli_env: dict[str, str]):
    _run(["init", "cfg-test"], cli_env)
    set_result = _run(["config", "set", "framework", "gemini-cli"], cli_env)
    assert set_result.returncode == 0
    get_result = _run(["config", "get", "framework"], cli_env)
    assert get_result.returncode == 0
    assert "gemini-cli" in get_result.stdout
