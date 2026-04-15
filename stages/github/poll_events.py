#!/usr/bin/env python3
"""Fetch GitHub events (issues, comments, PRs, reviews) since a timestamp.

Input:  { repo: Text, since: Text, token_env: Text }
Output: { events: List<Record>, polled_at: Text }

Effects: [Network, Fallible]
"""
import json
import os
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def execute(input: dict) -> dict:
    data = input
    repo = data["repo"]
    since = data.get("since", "1970-01-01T00:00:00Z")
    token_env = data.get("token_env", "GITHUB_TOKEN")
    token = os.environ.get(token_env, "")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    base = f"https://api.github.com/repos/{repo}"

    events = []

    def gh_get(path, params=""):
        url = f"{base}{path}?since={since}&per_page=100{params}"
        req = Request(url, headers=headers)
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            if e.code == 404:
                return []
            raise

    # Fetch issue events
    for item in gh_get("/issues/events"):
        event_type = item.get("event", "")
        issue = item.get("issue", {})
        if event_type == "labeled":
            events.append({
                "type": "label_added",
                "issue_number": issue.get("number"),
                "label": item.get("label", {}).get("name", ""),
                "actor": item.get("actor", {}).get("login", ""),
                "created_at": item.get("created_at", ""),
            })

    # Fetch issue comments (may contain feedback YAML)
    for item in gh_get("/issues/comments"):
        events.append({
            "type": "issue_comment",
            "issue_number": item.get("issue_url", "").split("/")[-1],
            "body": item.get("body", ""),
            "actor": item.get("user", {}).get("login", ""),
            "created_at": item.get("created_at", ""),
        })

    # Fetch open PRs (updated recently)
    for pr in gh_get("/pulls", "&state=open&sort=updated&direction=desc"):
        created = pr.get("created_at", "")
        if created >= since:
            # Extract linked issue from body
            body = pr.get("body", "") or ""
            linked_issue = None
            for word in body.split():
                if word.startswith("#") and word[1:].isdigit():
                    linked_issue = int(word[1:])
                    break

            events.append({
                "type": "pr_opened",
                "pr_number": pr.get("number"),
                "linked_issue": linked_issue,
                "actor": pr.get("user", {}).get("login", ""),
                "created_at": created,
            })

        # Check for reviews on this PR
        pr_num = pr.get("number")
        for review in gh_get(f"/pulls/{pr_num}/reviews"):
            if review.get("submitted_at", "") >= since:
                state = review.get("state", "").lower()
                events.append({
                    "type": "pr_review_submitted",
                    "pr_number": pr_num,
                    "review_state": "approved" if state == "approved"
                        else "changes_requested" if state == "changes_requested"
                        else "commented",
                    "actor": review.get("user", {}).get("login", ""),
                    "created_at": review.get("submitted_at", ""),
                })

        # Check if PR was merged
        if pr.get("merged_at") and pr["merged_at"] >= since:
            events.append({
                "type": "pr_merged",
                "pr_number": pr.get("number"),
                "actor": pr.get("merged_by", {}).get("login", ""),
                "created_at": pr["merged_at"],
            })

    # Sort by time
    events.sort(key=lambda e: e.get("created_at", ""))

    polled_at = datetime.now(UTC).isoformat()

    return {"events": events, "polled_at": polled_at}
