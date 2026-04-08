#!/usr/bin/env python3
"""Generate a sprint DAG from a brief and repo context.

Input:  { brief: Text, repo_context: Record, num_agents: Number }
Output: { dag: DagState }

Effects: [Llm, NonDeterministic]

Note: This is an LLM stage. It calls the model specified in CALORON_LLM_MODEL
(or defaults to a template-based fallback if no API key is available).
"""
import sys, json, os

data = json.load(sys.stdin)
brief = data["brief"]
context = data.get("repo_context", {})
num_agents = data.get("num_agents", 2)

# For now: template-based DAG generation (no LLM dependency).
# In production, this would call an LLM to decompose the brief into tasks.
# The template creates a simple sequential DAG.

sprint_id = f"sprint-{brief[:20].replace(' ', '-').lower()}"

# Simple heuristic: split brief into sentences/clauses as task titles
clauses = [c.strip() for c in brief.replace(",", ".").split(".") if c.strip()]
if not clauses:
    clauses = [brief]

tasks = {}
prev_id = None
for i, clause in enumerate(clauses[:6]):  # max 6 tasks
    tid = f"task-{i+1}"
    agent_idx = (i % num_agents) + 1
    tasks[tid] = {
        "id": tid,
        "title": clause,
        "status": "Pending",
        "depends_on": [prev_id] if prev_id and i > 0 else [],
        "agent_id": f"agent-{agent_idx}",
        "reviewer_id": "reviewer-1",
        "issue_number": None,
        "pr_number": None,
        "started_at": None,
        "completed_at": None,
        "intervention_count": 0,
    }
    prev_id = tid

dag = {
    "sprint_id": sprint_id,
    "tasks": tasks,
}

json.dump({"dag": dag}, sys.stdout)
