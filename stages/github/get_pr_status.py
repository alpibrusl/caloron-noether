#!/usr/bin/env python3
"""Get the status of a pull request (open, merged, closed, review state).

Input:  { repo: Text, pr_number: Number, token_env: Text }
Output: { state: Text, merged: Bool, review_state: Text, reviewers: List<Text> }

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

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Get PR
    req = Request(
        f"{host}/repos/{repo}/pulls/{pr_number}",
        headers=headers,
    )
    try:
        with urlopen(req) as resp:  # noqa: S310
            pr = json.loads(resp.read())
    except HTTPError as e:
        return {
            "state": "error",
            "merged": False,
            "review_state": "unknown",
            "reviewers": [],
            "error": str(e),
        }

    state = pr.get("state", "unknown")  # open, closed
    merged = pr.get("merged", False)

    # Get reviews
    review_state = "pending"
    reviewers: list[str] = []
    try:
        req = Request(
            f"{host}/repos/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
        )
        with urlopen(req) as resp:  # noqa: S310
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

    return {
        "state": state,
        "merged": merged,
        "review_state": review_state,
        "reviewers": reviewers,
    }
