#!/usr/bin/env python3
"""Create a GitHub issue.

Input:  { repo: Text, title: Text, body: Text, labels: List<Text>, token_env: Text }
Output: { issue_number: Number, url: Text }

Effects: [Network, Fallible]
"""
import json
import os
from urllib.request import Request, urlopen


def execute(input: dict) -> dict:
    data = input
    repo = data["repo"]
    token = os.environ.get(data.get("token_env", "GITHUB_TOKEN"), "")

    payload = json.dumps({
        "title": data["title"],
        "body": data.get("body", ""),
        "labels": data.get("labels", []),
    }).encode()

    req = Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(req) as resp:
        result = json.loads(resp.read())

    return {
        "issue_number": result["number"],
        "url": result["html_url"],
    }
