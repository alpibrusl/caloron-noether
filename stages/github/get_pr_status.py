#!/usr/bin/env python3
"""Get the status of a pull request (open, merged, closed, review state).

Input:  { repo: Text, pr_number: Number, token_env: Text }
Output: { state: Text, merged: Bool, review_state: Text, reviewers: List<Text> }

Effects: [Network, Fallible]
"""
import sys, json, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

data = json.load(sys.stdin)
repo = data["repo"]
pr_number = int(data["pr_number"])
token = os.environ.get(data.get("token_env", "GITHUB_TOKEN"), "")

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
}

# Get PR
req = Request(
    f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
    headers=headers,
)
try:
    with urlopen(req) as resp:
        pr = json.loads(resp.read())
except HTTPError as e:
    json.dump({
        "state": "error",
        "merged": False,
        "review_state": "unknown",
        "reviewers": [],
        "error": str(e),
    }, sys.stdout)
    sys.exit(0)

state = pr.get("state", "unknown")  # open, closed
merged = pr.get("merged", False)

# Get reviews
review_state = "pending"
reviewers = []
try:
    req = Request(
        f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews",
        headers=headers,
    )
    with urlopen(req) as resp:
        reviews = json.loads(resp.read())

    for review in reviews:
        reviewer = review.get("user", {}).get("login", "")
        if reviewer and reviewer not in reviewers:
            reviewers.append(reviewer)
        rs = review.get("state", "").lower()
        if rs == "approved":
            review_state = "approved"
        elif rs == "changes_requested":
            review_state = "changes_requested"
except HTTPError:
    pass

json.dump({
    "state": state,
    "merged": merged,
    "review_state": review_state,
    "reviewers": reviewers,
}, sys.stdout)
