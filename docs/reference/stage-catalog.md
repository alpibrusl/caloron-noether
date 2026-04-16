# Stage Catalog

The authoritative declaration is `stage_catalog.py` at the repo root —
this page summarises it. Every entry there has a corresponding Python
source file under `stages/<category>/<name>.py`.

`./register_stages.sh` registers all stages below with the local
Noether store and writes a `stage_ids.json` mapping
`name → SHA-256 hash` for use in compositions.

## Phase POs (LLM-driven planning)

Defined in `stages/phases/`; registered separately by
`./register_phases.sh` because they need an LLM-helper module inlined
at registration time.

| Stage | Effects | Input | Output |
|-------|---------|-------|--------|
| `design_po` | Pure (no-op pass-through today; placeholder for a future designer) | `{ goal, constraints }` | `{ goal, constraints, design_brief, components_inventory }` |
| `architect_po` | Llm, Network, NonDeterministic | `{ goal, constraints }` | `{ design_doc, components, risks }` |
| `dev_po` | Llm, Network, NonDeterministic | `{ components, design_doc, risks }` | `{ design_doc, components, risks, tasks }` |
| `review_po` | Pure | `{ tasks, design_doc }` | `{ design_doc, tasks, review_checks }` |
| `phases_to_sprint_tasks` | Pure | `{ tasks, review_checks, design_doc }` | `{ tasks }` (merged) |

## Sprint-tick reshape + KV stages

Defined in `stages/sprint/`. The `project_*` stages are tiny typed
realignment stages between `Let` bindings; the `load`/`save` stages
handle persistence between scheduler ticks.

| Stage | Effects | Purpose |
|-------|---------|---------|
| `load_tick_state` | Fallible | Load persisted state from `~/.caloron/kv/<sprint_id>.json` |
| `save_tick_state` | Fallible | Persist tick result back to disk (atomic write) |
| `build_tick_output` | Pure | Terminal: assemble `{actions_taken, errors, state, polled_at, interventions}` from accumulated scope |
| `project_poll_to_eval` | Pure | Reshape scope-with-poll-binding → `dag_evaluate` input |
| `project_health_to_intervention` | Pure | Reshape scope-with-health-binding → `decide_intervention` input |
| `project_all_to_execute` | Pure | Reshape accumulated scope → `execute_actions` input |

## DAG stages

| Stage | Effects | Input | Output |
|-------|---------|-------|--------|
| `dag_evaluate` | Pure | `{ state, events, stall_threshold_m }` | `{ state, actions }` |
| `dag_is_complete` | Pure | `{ state }` | `{ complete, total, done }` |
| `dag_validate` | Pure | `{ dag }` | `{ valid, errors }` |
| `unblocked_tasks` | Pure | `{ state }` | `{ ready_tasks }` |
| `execute_actions` | Network, Fallible | `{ repo, token_env, shell_url, dag_actions, supervisor_actions, sprint_id }` | `{ actions_taken, errors }` |

## GitHub / Gitea stages

All take an optional `host` field — defaults to `https://api.github.com`,
set to your Gitea API root (e.g. `http://gitea.local:3000/api/v1`) to
target a self-hosted forge. (Added in v0.4.1; both backends use the
same `/repos/<owner>/<repo>/...` endpoints.)

| Stage | Effects | Input | Output |
|-------|---------|-------|--------|
| `github_poll_events` | Network, Fallible | `{ repo, since, token_env, host }` | `{ events, polled_at }` |
| `github_create_issue` | Network, Fallible | `{ repo, title, body, labels, token_env, host }` | `{ issue_number, url }` |
| `github_post_comment` | Network, Fallible | `{ repo, issue_number, body, token_env, host }` | `{ comment_id, url }` |
| `github_add_label` | Network, Fallible | `{ repo, issue_number, label, token_env, host }` | `{ ok }` |
| `github_merge_pr` | Network, Fallible | `{ repo, pr_number, token_env, host }` | `{ merged, merge_commit }` |
| `get_pr_status` | Network, Fallible | `{ repo, pr_number, token_env, host }` | `{ state, merged, review_state, reviewers }` |

## Supervisor stages

| Stage | Effects | Input | Output |
|-------|---------|-------|--------|
| `check_agent_health` | Pure | `{ agents, stall_threshold_m }` | `{ results }` |
| `decide_intervention` | Pure | `{ results, interventions }` | `{ actions, updated_interventions }` |
| `compose_intervention_message` | Pure | `{ agent_id, task_title, health_status, action }` | `{ message }` |

## Retro stages

| Stage | Effects | Input | Output |
|-------|---------|-------|--------|
| `collect_sprint_feedback` | Network, Fallible | `{ repo, sprint_id, issue_numbers, token_env }` | `{ feedback_items }` |
| `compute_sprint_kpis` | Pure | `{ state, started_at, ended_at }` | `{ total_tasks, completed_tasks, completion_rate }` |
| `analyze_sprint_feedback` | Llm, Network, NonDeterministic | `{ feedback_items, kpis }` | `{ themes, improvements, learnings, sentiment }` |
| `write_retro_report` | Pure | `{ sprint_id, kpis, feedback_items, started_at, ended_at }` | `{ report_markdown }` |

## Kickoff stages

| Stage | Effects | Input | Output |
|-------|---------|-------|--------|
| `fetch_repo_context` | Network, Fallible | `{ repo, token_env, host }` | `{ description, open_issues, recent_commits, languages, default_branch }` |
| `generate_sprint_dag` | Llm, Network, NonDeterministic | `{ brief, repo_context, num_agents }` | `{ dag }` |

## Drift checks

`tests/test_stage_catalog.py` runs three checks against this catalog
on every CI run:

- Every declared entry has a Python source file on disk.
- Every source file exposes `execute()` at module level.
- No source file reads `sys.stdin` (the v0.3.4 migration; the runner
  handles I/O).
