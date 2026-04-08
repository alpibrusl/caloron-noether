#!/usr/bin/env python3
"""Merge a GitHub pull request.

Input:  { repo: Text, pr_number: Number, token_env: Text }
Output: { merged: Bool, merge_commit: Text }

Effects: [Network, Fallible]
"""
import sys, json, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

data = json.load(sys.stdin)
repo = data["repo"]
pr_number = int(data["pr_number"])
token = os.environ.get(data.get("token_env", "GITHUB_TOKEN"), "")

req = Request(
    f"https://api.github.com/repos/{repo}/pulls/{pr_number}/merge",
    data=b"{}",
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    },
    method="PUT",
)

try:
    with urlopen(req) as resp:
        result = json.loads(resp.read())
    json.dump({
        "merged": result.get("merged", False),
        "merge_commit": result.get("sha", ""),
    }, sys.stdout)
except HTTPError as e:
    json.dump({
        "merged": False,
        "merge_commit": "",
        "error": str(e),
    }, sys.stdout)
