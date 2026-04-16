#!/usr/bin/env python3
"""Add a label to a GitHub issue or PR.

Input:  { repo: Text, issue_number: Number, label: Text, token_env: Text }
Output: { ok: Bool }

Effects: [Network, Fallible]
"""
import json
import os
from urllib.request import Request, urlopen


def execute(input: dict) -> dict:
    repo = input["repo"]
    issue_number = int(input["issue_number"])
    token = os.environ.get(input.get("token_env", "GITHUB_TOKEN"), "")
    host = (input.get("host") or "https://api.github.com").rstrip("/")

    payload = json.dumps({"labels": [input["label"]]}).encode()

    req = Request(
        f"{host}/repos/{repo}/issues/{issue_number}/labels",
        data=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req) as resp:  # noqa: S310
            resp.read()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
