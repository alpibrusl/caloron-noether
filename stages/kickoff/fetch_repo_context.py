#!/usr/bin/env python3
"""Fetch repository context for sprint planning.

Input:  { repo: Text, token_env: Text }
Output: { description, open_issues, recent_commits, languages, default_branch }

Effects: [Network, Fallible]
"""
import json
import os
from urllib.request import Request, urlopen


def execute(input: dict) -> dict:
    data = input
    repo = data["repo"]
    token = os.environ.get(data.get("token_env", "GITHUB_TOKEN"), "")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    def gh_get(path):
        req = Request(f"https://api.github.com/repos/{repo}{path}", headers=headers)
        with urlopen(req) as resp:
            return json.loads(resp.read())

    # Repo info
    info = gh_get("")

    # Recent commits
    commits_raw = gh_get("/commits?per_page=5")
    recent_commits = [
        {
            "sha": c["sha"][:8],
            "message": c["commit"]["message"].split("\n")[0],
            "author": c["commit"]["author"]["name"],
            "date": c["commit"]["author"]["date"],
        }
        for c in commits_raw
    ]

    # Languages
    try:
        languages = gh_get("/languages")
    except Exception:
        languages = {}

    return {
        "description": info.get("description", ""),
        "open_issues": info.get("open_issues_count", 0),
        "recent_commits": recent_commits,
        "languages": languages,
        "default_branch": info.get("default_branch", "main"),
    }
