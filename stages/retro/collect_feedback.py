#!/usr/bin/env python3
"""Collect structured feedback from sprint issue comments.

Input:  { repo: Text, sprint_id: Text, issue_numbers: List<Number>, token_env: Text }
Output: { feedback_items: List<Record> }

Effects: [Network, Fallible]
"""
import json
import os
import re
from urllib.request import Request, urlopen

import yaml


def execute(input: dict) -> dict:
    data = input
    repo = data["repo"]
    issue_numbers = data.get("issue_numbers", [])
    token = os.environ.get(data.get("token_env", "GITHUB_TOKEN"), "")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    feedback_items = []

    for issue_num in issue_numbers:
        url = f"https://api.github.com/repos/{repo}/issues/{issue_num}/comments"
        req = Request(url, headers=headers)
        try:
            with urlopen(req) as resp:
                comments = json.loads(resp.read())
        except Exception:
            continue

        for comment in comments:
            body = comment.get("body", "")
            if "caloron_feedback:" not in body:
                continue

            # Extract YAML between --- markers
            match = re.search(r"---\s*\n(.*?)\n---", body, re.DOTALL)
            if not match:
                continue

            try:
                parsed = yaml.safe_load(match.group(1))
                if isinstance(parsed, dict) and "caloron_feedback" in parsed:
                    fb = parsed["caloron_feedback"]
                    feedback_items.append({
                        "issue_number": issue_num,
                        "author": comment.get("user", {}).get("login", ""),
                        "created_at": comment.get("created_at", ""),
                        "is_parsed_yaml": True,
                        "parsed": fb,
                    })
            except Exception:
                feedback_items.append({
                    "issue_number": issue_num,
                    "author": comment.get("user", {}).get("login", ""),
                    "created_at": comment.get("created_at", ""),
                    "is_parsed_yaml": False,
                    "parsed": None,
                    "raw_body": body[:500],
                })

    return {"feedback_items": feedback_items}
