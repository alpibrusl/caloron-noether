"""Tests for the ``host`` parameter on github_* / kickoff stages.

The pilot in v0.4.0 surfaced that the github_* stages hardcoded
``api.github.com`` while caloron's actual production usage is Gitea.
Adding a ``host`` input parameter lets the same stage catalogue target
either backend without duplication.

These tests don't make real HTTP calls — they monkeypatch ``urlopen``
to capture the URL the stage *would* hit and assert the host
substitution works.
"""

from __future__ import annotations

import sys
import unittest.mock
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    str(_REPO_ROOT),
    str(_REPO_ROOT / "stages" / "github"),
    str(_REPO_ROOT / "stages" / "kickoff"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _capture_urls(stage_module, kwargs: dict) -> list[str]:
    """Run ``stage_module.execute(kwargs)`` with urlopen mocked.

    Returns the list of full URLs the stage *attempted* to hit. The
    mocked urlopen raises after capturing so we get every URL the stage
    would have requested — many stages make multiple calls per execute.
    """
    captured: list[str] = []

    def fake_urlopen(req, *args, **kwargs):
        captured.append(req.full_url)
        raise RuntimeError("test stop — captured")

    with unittest.mock.patch.object(stage_module, "urlopen", fake_urlopen):
        try:
            stage_module.execute(kwargs)
        except Exception:
            pass
    return captured


# ── github_poll_events ──────────────────────────────────────────────────────


def test_poll_events_defaults_to_api_github_com():
    import poll_events

    urls = _capture_urls(
        poll_events,
        {"repo": "owner/repo", "since": "2026-01-01", "token_env": "X"},
    )
    assert urls
    assert urls[0].startswith("https://api.github.com/")


def test_poll_events_honours_explicit_host():
    import poll_events

    urls = _capture_urls(
        poll_events,
        {
            "repo": "owner/repo",
            "since": "2026-01-01",
            "token_env": "X",
            "host": "http://gitea.local:3000/api/v1",
        },
    )
    assert urls
    assert urls[0].startswith("http://gitea.local:3000/api/v1/")
    assert "api.github.com" not in urls[0]


def test_poll_events_strips_trailing_slash_from_host():
    import poll_events

    urls = _capture_urls(
        poll_events,
        {"repo": "o/r", "since": "1970", "token_env": "X",
         "host": "http://gitea.local:3000/api/v1/"},
    )
    # No double-slash between host and /repos/
    assert "/api/v1//repos/" not in urls[0]
    assert "/api/v1/repos/" in urls[0]


# ── github_create_issue ─────────────────────────────────────────────────────


def test_create_issue_honours_host():
    import create_issue

    urls = _capture_urls(
        create_issue,
        {
            "repo": "owner/repo",
            "title": "test",
            "body": "x",
            "labels": [],
            "token_env": "X",
            "host": "http://gitea.local:3000/api/v1",
        },
    )
    assert urls
    assert urls[0].startswith("http://gitea.local:3000/api/v1/repos/")


# ── github_post_comment ─────────────────────────────────────────────────────


def test_post_comment_honours_host():
    import post_comment

    urls = _capture_urls(
        post_comment,
        {
            "repo": "owner/repo",
            "issue_number": 1,
            "body": "x",
            "token_env": "X",
            "host": "http://gitea.local:3000/api/v1",
        },
    )
    assert urls
    assert urls[0].startswith("http://gitea.local:3000/api/v1/repos/")


# ── github_add_label ────────────────────────────────────────────────────────


def test_add_label_honours_host():
    import add_label

    urls = _capture_urls(
        add_label,
        {
            "repo": "owner/repo",
            "issue_number": 1,
            "label": "bug",
            "token_env": "X",
            "host": "http://gitea.local:3000/api/v1",
        },
    )
    assert urls
    assert urls[0].startswith("http://gitea.local:3000/api/v1/repos/")


# ── github_merge_pr ─────────────────────────────────────────────────────────


def test_merge_pr_honours_host():
    import merge_pr

    urls = _capture_urls(
        merge_pr,
        {
            "repo": "owner/repo",
            "pr_number": 1,
            "token_env": "X",
            "host": "http://gitea.local:3000/api/v1",
        },
    )
    assert urls
    assert urls[0].startswith("http://gitea.local:3000/api/v1/repos/")


# ── get_pr_status ───────────────────────────────────────────────────────────


def test_get_pr_status_honours_host():
    import get_pr_status

    urls = _capture_urls(
        get_pr_status,
        {
            "repo": "owner/repo",
            "pr_number": 1,
            "token_env": "X",
            "host": "http://gitea.local:3000/api/v1",
        },
    )
    assert urls
    assert urls[0].startswith("http://gitea.local:3000/api/v1/repos/")


# ── kickoff/fetch_repo_context ──────────────────────────────────────────────


def test_fetch_repo_context_honours_host():
    import fetch_repo_context

    urls = _capture_urls(
        fetch_repo_context,
        {
            "repo": "owner/repo",
            "token_env": "X",
            "host": "http://gitea.local:3000/api/v1",
        },
    )
    assert urls
    assert urls[0].startswith("http://gitea.local:3000/api/v1/repos/")


# ── Catalogue declares the field ────────────────────────────────────────────


@pytest.mark.parametrize(
    "stage_name",
    [
        "github_poll_events",
        "github_create_issue",
        "github_post_comment",
        "github_add_label",
        "github_merge_pr",
        "get_pr_status",
        "fetch_repo_context",
    ],
)
def test_catalogue_declares_host_field(stage_name: str):
    """Catch regression where someone updates a stage but not the catalogue."""
    sys.path.insert(0, str(_REPO_ROOT))
    from stage_catalog import CATALOG

    fields = [name for name, _type in CATALOG[stage_name]["input"]["Record"]]
    assert "host" in fields, (
        f"{stage_name}: stage source accepts `host` but catalogue declares "
        f"only {fields} — Noether type-check will reject the field"
    )
