"""Caloron stage catalogue — Noether v0.3 spec declarations.

One dict entry per stage, spelling out the input/output Record shape
in the ``[[key, type], ...]`` tuple form v0.3 uses. Keep descriptions
short and specific — the grid splitter and the semantic search both
read them.

Consumed by ``register_stages.sh`` (for shell invocation) and
``tests/test_stage_registration.py`` (to validate the catalogue stays
in sync with the stage source files on disk).
"""

from __future__ import annotations

from typing import Any

# Shorthand for the recurring "non-deterministic LLM call" effect set.
_LLM_EFFECTS = ["Llm", "NonDeterministic"]
_NET_EFFECTS = ["Network", "Fallible"]


# Each entry: {code_path, description, input, output, effects}.
# code_path is relative to the repo root; register_stages.sh reads it
# at registration time and inlines the source into the Noether spec.
CATALOG: dict[str, dict[str, Any]] = {
    # ── DAG stages ───────────────────────────────────────────────────────
    "dag_evaluate": {
        "code_path": "stages/dag/evaluate.py",
        "description": "Evaluate a sprint DAG from GitHub events; advance task states and emit actions.",
        "input": {
            "Record": [
                ["state", "Any"],
                ["events", {"List": "Any"}],
                ["stall_threshold_m", "Number"],
            ]
        },
        "output": {
            "Record": [
                ["state", "Any"],
                ["actions", {"List": "Any"}],
            ]
        },
        "effects": [],
    },
    "dag_is_complete": {
        "code_path": "stages/dag/is_complete.py",
        "description": "Check if a sprint DAG is complete.",
        "input": {"Record": [["state", "Any"]]},
        "output": {
            "Record": [
                ["complete", "Bool"],
                ["total", "Number"],
                ["done", "Number"],
            ]
        },
        "effects": [],
    },
    "dag_validate": {
        "code_path": "stages/dag/validate.py",
        "description": "Validate a sprint DAG for structural correctness.",
        "input": {"Record": [["dag", "Any"]]},
        "output": {
            "Record": [
                ["valid", "Bool"],
                ["errors", {"List": "Text"}],
            ]
        },
        "effects": [],
    },
    "unblocked_tasks": {
        "code_path": "stages/dag/unblocked_tasks.py",
        "description": "Return tasks that are Ready in the DAG.",
        "input": {"Record": [["state", "Any"]]},
        "output": {"Record": [["ready_tasks", {"List": "Any"}]]},
        "effects": [],
    },
    "execute_actions": {
        "code_path": "stages/dag/execute_actions.py",
        "description": "Execute DAG and supervisor actions via GitHub API and shell.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["token_env", "Text"],
                ["shell_url", "Text"],
                ["dag_actions", {"List": "Any"}],
                ["supervisor_actions", {"List": "Any"}],
                ["sprint_id", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["actions_taken", {"List": "Text"}],
                ["errors", {"List": "Text"}],
            ]
        },
        "effects": _NET_EFFECTS,
    },
    # ── GitHub stages ────────────────────────────────────────────────────
    "github_poll_events": {
        "code_path": "stages/github/poll_events.py",
        "description": "Poll GitHub for sprint events since a timestamp.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["since", "Text"],
                ["token_env", "Text"],
                ["host", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["events", {"List": "Any"}],
                ["polled_at", "Text"],
            ]
        },
        "effects": _NET_EFFECTS,
    },
    "github_create_issue": {
        "code_path": "stages/github/create_issue.py",
        "description": "Create a GitHub issue with title, body, and labels.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["title", "Text"],
                ["body", "Text"],
                ["labels", {"List": "Text"}],
                ["token_env", "Text"],
                ["host", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["issue_number", "Number"],
                ["url", "Text"],
            ]
        },
        "effects": _NET_EFFECTS,
    },
    "github_post_comment": {
        "code_path": "stages/github/post_comment.py",
        "description": "Post a comment on a GitHub issue or PR.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["issue_number", "Number"],
                ["body", "Text"],
                ["token_env", "Text"],
                ["host", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["comment_id", "Number"],
                ["url", "Text"],
            ]
        },
        "effects": _NET_EFFECTS,
    },
    "github_add_label": {
        "code_path": "stages/github/add_label.py",
        "description": "Add a label to a GitHub issue or PR.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["issue_number", "Number"],
                ["label", "Text"],
                ["token_env", "Text"],
                ["host", "Text"],
            ]
        },
        "output": {"Record": [["ok", "Bool"]]},
        "effects": _NET_EFFECTS,
    },
    "github_merge_pr": {
        "code_path": "stages/github/merge_pr.py",
        "description": "Merge a GitHub pull request.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["pr_number", "Number"],
                ["token_env", "Text"],
                ["host", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["merged", "Bool"],
                ["merge_commit", "Text"],
            ]
        },
        "effects": _NET_EFFECTS,
    },
    "get_pr_status": {
        "code_path": "stages/github/get_pr_status.py",
        "description": "Get the review status of a GitHub pull request.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["pr_number", "Number"],
                ["token_env", "Text"],
                ["host", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["state", "Text"],
                ["merged", "Bool"],
                ["review_state", "Text"],
                ["reviewers", {"List": "Text"}],
            ]
        },
        "effects": _NET_EFFECTS,
    },
    # ── Supervisor stages ────────────────────────────────────────────────
    "check_agent_health": {
        "code_path": "stages/supervisor/check_health.py",
        "description": "Check agent health from heartbeat history.",
        "input": {
            "Record": [
                ["agents", "Any"],
                ["stall_threshold_m", "Number"],
            ]
        },
        "output": {"Record": [["results", {"List": "Any"}]]},
        "effects": [],
    },
    "decide_intervention": {
        "code_path": "stages/supervisor/decide_intervention.py",
        "description": "Decide supervisor intervention for unhealthy agents.",
        "input": {
            "Record": [
                ["results", {"List": "Any"}],
                ["interventions", "Any"],
            ]
        },
        "output": {
            "Record": [
                ["actions", {"List": "Any"}],
                ["updated_interventions", "Any"],
            ]
        },
        "effects": [],
    },
    "compose_intervention_message": {
        "code_path": "stages/supervisor/compose_message.py",
        "description": "Compose a GitHub comment for a supervisor intervention.",
        "input": {
            "Record": [
                ["agent_id", "Text"],
                ["task_title", "Text"],
                ["health_status", "Text"],
                ["action", "Text"],
            ]
        },
        "output": {"Record": [["message", "Text"]]},
        "effects": [],
    },
    # ── Retro stages ─────────────────────────────────────────────────────
    "collect_sprint_feedback": {
        "code_path": "stages/retro/collect_feedback.py",
        "description": "Collect structured feedback from sprint issue comments.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["sprint_id", "Text"],
                ["issue_numbers", {"List": "Number"}],
                ["token_env", "Text"],
            ]
        },
        "output": {"Record": [["feedback_items", {"List": "Any"}]]},
        "effects": _NET_EFFECTS,
    },
    "compute_sprint_kpis": {
        "code_path": "stages/retro/compute_kpis.py",
        "description": "Compute sprint KPIs from final DAG state.",
        "input": {
            "Record": [
                ["state", "Any"],
                ["started_at", "Text"],
                ["ended_at", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["total_tasks", "Number"],
                ["completed_tasks", "Number"],
                ["completion_rate", "Number"],
            ]
        },
        "effects": [],
    },
    "write_retro_report": {
        "code_path": "stages/retro/write_report.py",
        "description": "Generate a sprint retro report in Markdown.",
        "input": {
            "Record": [
                ["sprint_id", "Text"],
                ["kpis", "Any"],
                ["feedback_items", {"List": "Any"}],
                ["started_at", "Text"],
                ["ended_at", "Text"],
            ]
        },
        "output": {"Record": [["report_markdown", "Text"]]},
        "effects": [],
    },
    "analyze_sprint_feedback": {
        "code_path": "stages/retro/analyze_feedback.py",
        "description": "Analyze sprint feedback into themes, improvements, and learnings.",
        "input": {
            "Record": [
                ["feedback_items", {"List": "Any"}],
                ["kpis", "Any"],
            ]
        },
        "output": {
            "Record": [
                ["themes", {"List": "Text"}],
                ["improvements", {"List": "Text"}],
                ["learnings", {"List": "Text"}],
                ["sentiment", "Text"],
            ]
        },
        "effects": _LLM_EFFECTS,
    },
    # ── Sprint-tick boundary reshape stages ──────────────────────────────
    # These exist purely to realign data between the domain stages above
    # and the sprint_tick composition chain. Each one is narrow and
    # typed so the composition dry-run-checks end-to-end, and so the
    # data flow in the graph remains explicit rather than hidden inside
    # a monolithic Python stage.
    "project_poll_to_eval": {
        "code_path": "stages/sprint/project_poll_to_eval.py",
        "description": "Reshape scope-with-poll-binding into dag_evaluate input.",
        "input": {
            "Record": [
                ["state", "Any"],
                ["poll", "Any"],
                ["stall_threshold_m", "Number"],
            ]
        },
        "output": {
            "Record": [
                ["state", "Any"],
                ["events", {"List": "Any"}],
                ["stall_threshold_m", "Number"],
            ]
        },
        "effects": [],
    },
    "project_health_to_intervention": {
        "code_path": "stages/sprint/project_health_to_intervention.py",
        "description": "Reshape scope-with-health-binding into decide_intervention input.",
        "input": {
            "Record": [
                ["health", "Any"],
                ["interventions", "Any"],
            ]
        },
        "output": {
            "Record": [
                ["results", {"List": "Any"}],
                ["interventions", "Any"],
            ]
        },
        "effects": [],
    },
    "load_tick_state": {
        "code_path": "stages/sprint/load_tick_state.py",
        "description": "Load persisted sprint-tick state from caloron's KV directory.",
        "input": {
            "Record": [
                ["sprint_id", "Text"],
                ["repo", "Text"],
                ["stall_threshold_m", "Number"],
                ["token_env", "Text"],
                ["shell_url", "Text"],
                ["host", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["sprint_id", "Text"],
                ["repo", "Text"],
                ["stall_threshold_m", "Number"],
                ["token_env", "Text"],
                ["shell_url", "Text"],
                ["host", "Text"],
                ["state", "Any"],
                ["agents", "Any"],
                ["interventions", "Any"],
                ["since", "Text"],
            ]
        },
        "effects": ["Fallible"],
    },
    "save_tick_state": {
        "code_path": "stages/sprint/save_tick_state.py",
        "description": "Persist sprint-tick result to caloron's KV directory.",
        "input": {
            "Record": [
                ["sprint_id", "Text"],
                ["tick_result", "Any"],
            ]
        },
        "output": {
            "Record": [
                ["actions_taken", {"List": "Text"}],
                ["errors", {"List": "Text"}],
                ["persisted_path", "Text"],
            ]
        },
        "effects": ["Fallible"],
    },
    "build_tick_output": {
        "code_path": "stages/sprint/build_tick_output.py",
        "description": "Terminal reshape: accumulated tick scope into rich result record for persistence.",
        "input": {
            "Record": [
                ["execute_result", "Any"],
                ["eval", "Any"],
                ["poll", "Any"],
                ["supervisor", "Any"],
            ]
        },
        "output": {
            "Record": [
                ["actions_taken", {"List": "Text"}],
                ["errors", {"List": "Text"}],
                ["state", "Any"],
                ["polled_at", "Text"],
                ["interventions", "Any"],
            ]
        },
        "effects": [],
    },
    "project_all_to_execute": {
        "code_path": "stages/sprint/project_all_to_execute.py",
        "description": "Reshape accumulated sprint-tick scope into execute_actions input.",
        "input": {
            "Record": [
                ["eval", "Any"],
                ["supervisor", "Any"],
                ["repo", "Text"],
                ["token_env", "Text"],
                ["shell_url", "Text"],
                ["sprint_id", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["repo", "Text"],
                ["token_env", "Text"],
                ["shell_url", "Text"],
                ["dag_actions", {"List": "Any"}],
                ["supervisor_actions", {"List": "Any"}],
                ["sprint_id", "Text"],
            ]
        },
        "effects": [],
    },
    # ── Kickoff stages ───────────────────────────────────────────────────
    "fetch_repo_context": {
        "code_path": "stages/kickoff/fetch_repo_context.py",
        "description": "Fetch repository context for sprint planning.",
        "input": {
            "Record": [
                ["repo", "Text"],
                ["token_env", "Text"],
                ["host", "Text"],
            ]
        },
        "output": {
            "Record": [
                ["description", "Text"],
                ["open_issues", "Number"],
                ["recent_commits", {"List": "Any"}],
                ["languages", "Any"],
                ["default_branch", "Text"],
            ]
        },
        "effects": _NET_EFFECTS,
    },
    "generate_sprint_dag": {
        "code_path": "stages/kickoff/generate_dag.py",
        "description": "Generate a sprint DAG from a brief and repo context.",
        "input": {
            "Record": [
                ["brief", "Text"],
                ["repo_context", "Any"],
                ["num_agents", "Number"],
            ]
        },
        "output": {"Record": [["dag", "Any"]]},
        "effects": _LLM_EFFECTS,
    },
}
