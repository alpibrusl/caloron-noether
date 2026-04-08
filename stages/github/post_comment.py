#!/usr/bin/env python3
"""Post a comment on a GitHub issue or PR.

Input:  { repo: Text, issue_number: Number, body: Text, token_env: Text }
Output: { comment_id: Number, url: Text }

Effects: [Network, Fallible]
"""
import sys, json, os
from urllib.request import Request, urlopen

data = json.load(sys.stdin)
repo = data["repo"]
issue_number = int(data["issue_number"])
token = os.environ.get(data.get("token_env", "GITHUB_TOKEN"), "")

payload = json.dumps({"body": data["body"]}).encode()

req = Request(
    f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
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

json.dump({
    "comment_id": result["id"],
    "url": result["html_url"],
}, sys.stdout)
