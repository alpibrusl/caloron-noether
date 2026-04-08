# Stages

Every piece of business logic is a Noether stage — a typed function that reads JSON from stdin and writes JSON to stdout.

## Stage Contract

```python
#!/usr/bin/env python3
import sys, json

input_data = json.load(sys.stdin)
# ... logic ...
json.dump(output_data, sys.stdout)
```

Noether wraps this with type checking, effect tracking, and output caching.

## DAG Stages (Pure)

No side effects. Deterministic. Cached by input hash.

### `dag_evaluate`

Advances task states based on GitHub events.

- **Input:** `{ state: DagState, events: List<Event>, stall_threshold_m: Number }`
- **Output:** `{ state: DagState, actions: List<Action> }`
- Handles: PR merge → Done, PR open → InReview, dependency unblocking, stall detection

### `dag_is_complete`

- **Input:** `{ state: DagState }`
- **Output:** `{ complete: Bool, total: Number, done: Number }`

### `dag_validate`

Cycle detection and reference checking.

- **Input:** `{ dag: DagState }`
- **Output:** `{ valid: Bool, errors: List<Text> }`

## GitHub Stages (Network, Fallible)

All use `GITHUB_TOKEN` from environment. Work with both GitHub and Gitea APIs.

| Stage | Input | Output |
|-------|-------|--------|
| `poll_events` | repo, since, token_env | events, polled_at |
| `create_issue` | repo, title, body, labels | issue_number, url |
| `post_comment` | repo, issue_number, body | comment_id, url |
| `add_label` | repo, issue_number, label | ok |
| `merge_pr` | repo, pr_number | merged, merge_commit |

## Supervisor Stages (Pure)

### `check_agent_health`

Classifies each agent as healthy, stalled, or missing.

- **Input:** `{ agents: Map, stall_threshold_m: Number }`
- **Output:** `{ results: List<{ agent_id, status, minutes_since }> }`

### `decide_intervention`

Implements the probe → restart → escalate ladder.

- **Input:** `{ results: List, interventions: Map }`
- **Output:** `{ actions: List<{ agent_id, action, reason }> }`

### `compose_intervention_message`

Generates a GitHub comment for the intervention.

- **Input:** `{ agent_id, task_title, health_status, action }`
- **Output:** `{ message: Text }`

## Retro Stages

| Stage | Effects | Description |
|-------|---------|-------------|
| `collect_feedback` | Network | Fetch feedback YAML from issue comments |
| `compute_kpis` | Pure | Completion rate, velocity, interventions |
| `write_report` | Pure | Generate Markdown retro report |

## Kickoff Stages

| Stage | Effects | Description |
|-------|---------|-------------|
| `fetch_repo_context` | Network | Repo description, commits, languages |
| `generate_dag` | Pure/LLM | Generate DAG from brief (template-based or LLM) |

## Testing Stages

Each stage can be tested directly:

```bash
echo '{"state": {"tasks": {"t1": {"status": "Pending", "depends_on": []}}}, "events": [], "stall_threshold_m": 20}' \
  | python3 stages/dag/evaluate.py \
  | python3 -m json.tool
```
