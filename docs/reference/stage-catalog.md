# Stage Catalog

All 16 custom stages registered with the Noether store.

## DAG Stages

| Stage | Description | Effects | Input | Output |
|-------|-------------|---------|-------|--------|
| `dag_evaluate` | Advance task states from events | Pure | state, events, stall_threshold_m | state, actions |
| `dag_is_complete` | Check if sprint is done | Pure | state | complete, total, done |
| `dag_validate` | Validate DAG structure | Pure | dag | valid, errors |

## GitHub Stages

| Stage | Description | Effects | Input | Output |
|-------|-------------|---------|-------|--------|
| `github_poll_events` | Fetch events since timestamp | Network, Fallible | repo, since, token_env | events, polled_at |
| `github_create_issue` | Create an issue | Network, Fallible | repo, title, body, labels | issue_number, url |
| `github_post_comment` | Post a comment | Network, Fallible | repo, issue_number, body | comment_id, url |
| `github_add_label` | Add a label | Network, Fallible | repo, issue_number, label | ok |
| `github_merge_pr` | Merge a PR | Network, Fallible | repo, pr_number | merged, merge_commit |

## Supervisor Stages

| Stage | Description | Effects | Input | Output |
|-------|-------------|---------|-------|--------|
| `check_agent_health` | Classify agent health | Pure | agents, stall_threshold_m | results |
| `decide_intervention` | Choose intervention action | Pure | results, interventions | actions, updated_interventions |
| `compose_message` | Generate intervention comment | Pure | agent_id, task_title, status, action | message |

## Retro Stages

| Stage | Description | Effects | Input | Output |
|-------|-------------|---------|-------|--------|
| `collect_feedback` | Fetch feedback from comments | Network, Fallible | repo, sprint_id, issue_numbers | feedback_items |
| `compute_kpis` | Calculate sprint metrics | Pure | state, started_at, ended_at | KPI record |
| `write_report` | Generate Markdown report | Pure | sprint_id, kpis, feedback | report_markdown |

## Kickoff Stages

| Stage | Description | Effects | Input | Output |
|-------|-------------|---------|-------|--------|
| `fetch_repo_context` | Fetch repo metadata | Network, Fallible | repo | description, commits, languages |
| `generate_dag` | Generate DAG from brief | Pure | brief, repo_context, num_agents | dag |
