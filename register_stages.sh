#!/bin/bash
# Register all custom Caloron stages with the Noether store.
# Run this once after setting up the project.
# Stage IDs will be printed — copy them into the composition graphs.

set -euo pipefail

NOETHER="${NOETHER_BIN:-noether}"
STAGES_DIR="$(dirname "$0")/stages"
SPECS_DIR="$(dirname "$0")/stage-specs"

mkdir -p "$SPECS_DIR"

echo "Registering Caloron stages with Noether..."
echo "============================================"

register() {
    local name="$1"
    local description="$2"
    local input_type="$3"
    local output_type="$4"
    local effects="$5"
    local language="$6"
    local code_file="$7"

    local code
    code=$(cat "$code_file")

    local spec_file="$SPECS_DIR/${name}.json"

    # Build the spec JSON
    python3 -c "
import json, sys
spec = {
    'description': '''$description''',
    'input': $input_type,
    'output': $output_type,
    'effects': $effects,
    'capabilities': [],
    'implementation': {
        'language': '$language',
        'code': open('$code_file').read()
    }
}
json.dump(spec, open('$spec_file', 'w'), indent=2)
"

    echo -n "  $name: "
    $NOETHER stage add "$spec_file" 2>&1 | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    if data.get('ok'):
        stage_id = data.get('data', {}).get('id', '???')
        print(f'{stage_id}')
    else:
        print(f'ERROR: {data.get(\"error\", {}).get(\"message\", \"unknown\")}')
except:
    print('ERROR: could not parse response')
"
}

# === DAG stages (Pure) ===
register "dag_evaluate" \
    "Evaluate a sprint DAG from GitHub events" \
    '{"type": "Record", "fields": {"state": "Any", "events": {"type": "List", "element": "Any"}, "stall_threshold_m": "Number"}}' \
    '{"type": "Record", "fields": {"state": "Any", "actions": {"type": "List", "element": "Any"}}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/dag/evaluate.py"

register "dag_is_complete" \
    "Check if a sprint DAG is complete" \
    '{"type": "Record", "fields": {"state": "Any"}}' \
    '{"type": "Record", "fields": {"complete": "Bool", "total": "Number", "done": "Number"}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/dag/is_complete.py"

register "dag_validate" \
    "Validate a sprint DAG for structural correctness" \
    '{"type": "Record", "fields": {"dag": "Any"}}' \
    '{"type": "Record", "fields": {"valid": "Bool", "errors": {"type": "List", "element": "Text"}}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/dag/validate.py"

# === GitHub stages (Network, Fallible) ===
register "github_poll_events" \
    "Poll GitHub for sprint events since a timestamp" \
    '{"type": "Record", "fields": {"repo": "Text", "since": "Text", "token_env": "Text"}}' \
    '{"type": "Record", "fields": {"events": {"type": "List", "element": "Any"}, "polled_at": "Text"}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/github/poll_events.py"

register "github_create_issue" \
    "Create a GitHub issue with title, body, and labels" \
    '{"type": "Record", "fields": {"repo": "Text", "title": "Text", "body": "Text", "labels": {"type": "List", "element": "Text"}, "token_env": "Text"}}' \
    '{"type": "Record", "fields": {"issue_number": "Number", "url": "Text"}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/github/create_issue.py"

register "github_post_comment" \
    "Post a comment on a GitHub issue or PR" \
    '{"type": "Record", "fields": {"repo": "Text", "issue_number": "Number", "body": "Text", "token_env": "Text"}}' \
    '{"type": "Record", "fields": {"comment_id": "Number", "url": "Text"}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/github/post_comment.py"

register "github_add_label" \
    "Add a label to a GitHub issue or PR" \
    '{"type": "Record", "fields": {"repo": "Text", "issue_number": "Number", "label": "Text", "token_env": "Text"}}' \
    '{"type": "Record", "fields": {"ok": "Bool"}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/github/add_label.py"

register "github_merge_pr" \
    "Merge a GitHub pull request" \
    '{"type": "Record", "fields": {"repo": "Text", "pr_number": "Number", "token_env": "Text"}}' \
    '{"type": "Record", "fields": {"merged": "Bool", "merge_commit": "Text"}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/github/merge_pr.py"

# === Supervisor stages ===
register "check_agent_health" \
    "Check agent health from heartbeat history" \
    '{"type": "Record", "fields": {"agents": "Any", "stall_threshold_m": "Number"}}' \
    '{"type": "Record", "fields": {"results": {"type": "List", "element": "Any"}}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/supervisor/check_health.py"

register "decide_intervention" \
    "Decide supervisor intervention for unhealthy agents" \
    '{"type": "Record", "fields": {"results": {"type": "List", "element": "Any"}, "interventions": "Any"}}' \
    '{"type": "Record", "fields": {"actions": {"type": "List", "element": "Any"}, "updated_interventions": "Any"}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/supervisor/decide_intervention.py"

register "compose_intervention_message" \
    "Compose a GitHub comment for a supervisor intervention" \
    '{"type": "Record", "fields": {"agent_id": "Text", "task_title": "Text", "health_status": "Text", "action": "Text"}}' \
    '{"type": "Record", "fields": {"message": "Text"}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/supervisor/compose_message.py"

# === Retro stages ===
register "collect_sprint_feedback" \
    "Collect structured feedback from sprint issue comments" \
    '{"type": "Record", "fields": {"repo": "Text", "sprint_id": "Text", "issue_numbers": {"type": "List", "element": "Number"}, "token_env": "Text"}}' \
    '{"type": "Record", "fields": {"feedback_items": {"type": "List", "element": "Any"}}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/retro/collect_feedback.py"

register "compute_sprint_kpis" \
    "Compute sprint KPIs from final DAG state" \
    '{"type": "Record", "fields": {"state": "Any", "started_at": "Text", "ended_at": "Text"}}' \
    '{"type": "Record", "fields": {"total_tasks": "Number", "completed_tasks": "Number", "completion_rate": "Number"}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/retro/compute_kpis.py"

register "write_retro_report" \
    "Generate a sprint retro report in Markdown" \
    '{"type": "Record", "fields": {"sprint_id": "Text", "kpis": "Any", "feedback_items": {"type": "List", "element": "Any"}, "started_at": "Text", "ended_at": "Text"}}' \
    '{"type": "Record", "fields": {"report_markdown": "Text"}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/retro/write_report.py"

# === Kickoff stages ===
register "fetch_repo_context" \
    "Fetch repository context for sprint planning" \
    '{"type": "Record", "fields": {"repo": "Text", "token_env": "Text"}}' \
    '{"type": "Record", "fields": {"description": "Text", "open_issues": "Number", "recent_commits": {"type": "List", "element": "Any"}, "languages": "Any", "default_branch": "Text"}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/kickoff/fetch_repo_context.py"

register "generate_sprint_dag" \
    "Generate a sprint DAG from a brief and repo context" \
    '{"type": "Record", "fields": {"brief": "Text", "repo_context": "Any", "num_agents": "Number"}}' \
    '{"type": "Record", "fields": {"dag": "Any"}}' \
    '[{"effect": "Llm"}, {"effect": "NonDeterministic"}]' \
    "python3" \
    "$STAGES_DIR/kickoff/generate_dag.py"

# === New stages (from review) ===

register "analyze_sprint_feedback" \
    "Analyze sprint feedback into themes, improvements, and learnings" \
    '{"type": "Record", "fields": {"feedback_items": {"type": "List", "element": "Any"}, "kpis": "Any"}}' \
    '{"type": "Record", "fields": {"themes": {"type": "List", "element": "Text"}, "improvements": {"type": "List", "element": "Text"}, "learnings": {"type": "List", "element": "Text"}, "sentiment": "Text"}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/retro/analyze_feedback.py"

register "unblocked_tasks" \
    "Return tasks that are Ready in the DAG" \
    '{"type": "Record", "fields": {"state": "Any"}}' \
    '{"type": "Record", "fields": {"ready_tasks": {"type": "List", "element": "Any"}}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/dag/unblocked_tasks.py"

register "get_pr_status" \
    "Get the review status of a GitHub pull request" \
    '{"type": "Record", "fields": {"repo": "Text", "pr_number": "Number", "token_env": "Text"}}' \
    '{"type": "Record", "fields": {"state": "Text", "merged": "Bool", "review_state": "Text", "reviewers": {"type": "List", "element": "Text"}}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/github/get_pr_status.py"

register "execute_actions" \
    "Execute DAG and supervisor actions via GitHub API and shell" \
    '{"type": "Record", "fields": {"repo": "Text", "token_env": "Text", "shell_url": "Text", "dag_actions": {"type": "List", "element": "Any"}, "supervisor_actions": {"type": "List", "element": "Any"}, "sprint_id": "Text"}}' \
    '{"type": "Record", "fields": {"actions_taken": {"type": "List", "element": "Text"}, "errors": {"type": "List", "element": "Text"}}}' \
    '[{"effect": "Network"}, {"effect": "Fallible"}]' \
    "python3" \
    "$STAGES_DIR/dag/execute_actions.py"

# === Phase stages (multi-role sprints) ===
register "architect_po" \
    "Architect PO — decompose a goal into components, design doc, and risks" \
    '{"type": "Record", "fields": {"goal": "Text", "constraints": "Text"}}' \
    '{"type": "Record", "fields": {"design_doc": "Text", "components": {"type": "List", "element": "Any"}, "risks": {"type": "List", "element": "Text"}}}' \
    '[{"effect": "Llm"}, {"effect": "NonDeterministic"}]' \
    "python3" \
    "$STAGES_DIR/phases/architect_po.py"

register "dev_po" \
    "Dev PO — turn architect components into concrete agent tasks" \
    '{"type": "Record", "fields": {"components": {"type": "List", "element": "Any"}, "sprint_id": "Text", "framework": "Text"}}' \
    '{"type": "Record", "fields": {"tasks": {"type": "List", "element": "Any"}}}' \
    '[{"effect": "Pure"}]' \
    "python3" \
    "$STAGES_DIR/phases/dev_po.py"

echo ""
echo "Done. Now replace REGISTER:* placeholders in compositions/*.json:"
echo ""
echo "  For each registered stage, run:"
echo "    noether stage search '<description>' | jq '.data.stages[0].id'"
echo ""
echo "  Then replace REGISTER:<name> with the real hash in the composition files."
echo ""
echo "  Or run: noether run --dry-run compositions/sprint_tick.json --input '{...}'"
echo "  to type-check the graphs."
