#!/usr/bin/env python3
"""Check if a sprint's DAG is complete (all tasks in terminal state).

Input:  { state: DagState }
Output: { complete: Bool, total: Number, done: Number, blocked: Number }

Pure stage.
"""
import sys, json

data = json.load(sys.stdin)
tasks = data["state"]["tasks"]

total = len(tasks)
done = sum(1 for t in tasks.values() if t["status"] == "Done")
blocked = sum(1 for t in tasks.values() if t["status"] in ("Blocked", "Escalated"))
cancelled = sum(1 for t in tasks.values() if t["status"] == "Cancelled")

terminal = done + blocked + cancelled
complete = terminal == total and total > 0

json.dump({
    "complete": complete,
    "total": total,
    "done": done,
    "blocked": blocked,
    "cancelled": cancelled,
}, sys.stdout)
