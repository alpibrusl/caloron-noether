#!/usr/bin/env python3
"""Add a label to a GitHub issue or PR.

Input:  { repo: Text, issue_number: Number, label: Text, token_env: Text }
Output: { ok: Bool }

Effects: [Network, Fallible]
"""
import sys, json, os
from urllib.request import Request, urlopen

data = json.load(sys.stdin)
repo = data["repo"]
issue_number = int(data["issue_number"])
token = os.environ.get(data.get("token_env", "GITHUB_TOKEN"), "")

payload = json.dumps({"labels": [data["label"]]}).encode()

req = Request(
    f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels",
    data=payload,
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urlopen(req) as resp:
        resp.read()
    json.dump({"ok": True}, sys.stdout)
except Exception as e:
    json.dump({"ok": False, "error": str(e)}, sys.stdout)
