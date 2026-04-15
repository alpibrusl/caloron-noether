"""Scaffold selection — don't inject FastAPI into a CLI project.

Field report (2026-04-15): a pure CLI tool project got a FastAPI main.py
and Dockerfile because the FastAPI template matched on the generic
keyword "api" even though the goal was clearly a command-line tool.

Fix layers tested here:

- Overly-generic keywords like "api" / "endpoint" removed from the
  FastAPI templates in favour of more specific phrases ("fastapi",
  "rest api", "web service").
- New ``anti_keywords`` field on templates: CLI-signalling words
  ("cli", "argparse", "click", "command-line") penalise web-framework
  templates by -3, so they lose to the dedicated CLI scaffold.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORCH_DIR = _REPO_ROOT / "orchestrator"
for _p in (str(_REPO_ROOT), str(_ORCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def template_store():
    import importlib

    import template_store as ts

    importlib.reload(ts)
    return ts


def _scaffold(ts, goal: str, skills: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        return ts.scaffold_project(tmp, skills, goal)


def test_cli_goal_does_not_scaffold_fastapi(template_store):
    """The bug from the field report: 'CLI tool' goal picked FastAPI."""
    result = _scaffold(
        template_store,
        "Build a CLI tool to scrape campaign data from Google Ads API",
        ["python-development"],
    )
    # Whatever matches, it must not be a FastAPI web scaffold.
    assert result["template"] != "fastapi"
    assert result["template"] != "fastapi-postgres"


def test_fastapi_goal_still_matches_fastapi(template_store):
    """We haven't killed the happy path."""
    result = _scaffold(
        template_store,
        "Build a FastAPI service with REST API endpoints for users",
        ["rest-api-development", "python-development"],
    )
    assert result["template"] == "fastapi"


def test_cli_goal_matches_cli_template(template_store):
    """CLI goal picks the CLI scaffold, not nothing."""
    result = _scaffold(
        template_store,
        "Build a command-line tool using click to process CSV files",
        ["python-development"],
    )
    assert result["template"] == "python-cli"


def test_generic_api_word_does_not_trigger_fastapi(template_store):
    """Mentioning 'API' in a non-web sense (e.g. 'consume an API') is
    not enough to pick FastAPI — requires explicit fastapi/web-service
    signal."""
    result = _scaffold(
        template_store,
        "Build a CLI that fetches data from the GitHub API",
        ["python-development"],
    )
    # CLI scaffold should win over the weakened FastAPI match.
    assert result["template"] != "fastapi"
