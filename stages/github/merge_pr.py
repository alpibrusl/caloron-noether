#!/usr/bin/env python3
"""Merge a GitHub pull request.

Input:  { repo: Text, pr_number: Number, token_env: Text }
Output: { merged: Bool, merge_commit: Text }

Effects: [Network, Fallible]
"""
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def execute(input: dict) -> dict:
    repo = input["repo"]
    pr_number = int(input["pr_number"])
    token = os.environ.get(input.get("token_env", "GITHUB_TOKEN"), "")
    host = (input.get("host") or "https://api.github.com").rstrip("/")

    req = Request(
        f"{host}/repos/{repo}/pulls/{pr_number}/merge",
        data=b"{}",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="PUT",
    )

    try:
        with urlopen(req) as resp:  # noqa: S310
            result = json.loads(resp.read())
        return {
            "merged": result.get("merged", False),
            "merge_commit": result.get("sha", ""),
        }
    except HTTPError as e:
        return {
            "merged": False,
            "merge_commit": "",
            "error": str(e),
        }
