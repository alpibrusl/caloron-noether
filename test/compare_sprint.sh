#!/bin/bash
# Comparative sprint test: exercises the same scenario through
# both the caloron-noether Python stages and the Gitea API.
#
# Prerequisites:
#   - Gitea running in Docker (docker exec gitea ...)
#   - Repo caloron/test-project exists
#   - Python3 available

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
STAGES_DIR="$PROJECT_DIR/stages"

source "$SCRIPT_DIR/gitea_api.sh"

REPO="caloron/test-project"
SPRINT_ID="sprint-compare-$(date +%s)"

echo "=========================================="
echo " Caloron Comparative Sprint Test"
echo " Sprint: $SPRINT_ID"
echo " Repo: $REPO (Gitea)"
echo "=========================================="
echo ""

# ============================================================
# Phase 1: Create a DAG (like kickoff)
# ============================================================
echo "--- Phase 1: Generate DAG ---"

DAG_INPUT=$(cat <<EOF
{
  "brief": "Add health endpoint. Add metrics endpoint that depends on health.",
  "repo_context": {"description": "Test project", "open_issues": 0, "recent_commits": [], "languages": {"Python": 100}, "default_branch": "main"},
  "num_agents": 2
}
EOF
)

DAG_OUTPUT=$(echo "$DAG_INPUT" | python3 "$STAGES_DIR/kickoff/generate_dag.py")
echo "Generated DAG:"
echo "$DAG_OUTPUT" | python3 -m json.tool
echo ""

# Extract the DAG state
DAG_STATE=$(echo "$DAG_OUTPUT" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['dag']))")

# ============================================================
# Phase 2: Validate DAG
# ============================================================
echo "--- Phase 2: Validate DAG ---"

VALIDATE_OUTPUT=$(echo "{\"dag\": $DAG_STATE}" | python3 "$STAGES_DIR/dag/validate.py")
VALID=$(echo "$VALIDATE_OUTPUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['valid'])")
echo "Valid: $VALID"
if [ "$VALID" != "True" ]; then
    echo "DAG validation failed!"
    echo "$VALIDATE_OUTPUT" | python3 -m json.tool
    exit 1
fi
echo ""

# ============================================================
# Phase 3: Create issues on Gitea
# ============================================================
echo "--- Phase 3: Create Issues on Gitea ---"

TASK_IDS=$(echo "$DAG_STATE" | python3 -c "import json,sys; [print(k) for k in json.load(sys.stdin)['tasks']]")

for TASK_ID in $TASK_IDS; do
    TITLE=$(echo "$DAG_STATE" | python3 -c "import json,sys; print(json.load(sys.stdin)['tasks']['$TASK_ID']['title'])")

    ISSUE_RESULT=$(gitea_post "/api/v1/repos/$REPO/issues" \
        "{\"title\": \"$TITLE\", \"body\": \"Sprint: $SPRINT_ID\\nTask: $TASK_ID\", \"labels\": []}")

    ISSUE_NUM=$(echo "$ISSUE_RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['number'])")
    echo "  $TASK_ID → Issue #$ISSUE_NUM ($TITLE)"

    # Update DAG state with issue number
    DAG_STATE=$(echo "$DAG_STATE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
d['tasks']['$TASK_ID']['issue_number'] = $ISSUE_NUM
json.dump(d, sys.stdout)
")
done
echo ""

# ============================================================
# Phase 4: Run sprint tick (no events yet → unblock Ready tasks)
# ============================================================
echo "--- Phase 4: Sprint Tick 1 (initial) ---"

TICK_INPUT=$(cat <<EOF
{"state": $DAG_STATE, "events": [], "stall_threshold_m": 60}
EOF
)

TICK_OUTPUT=$(echo "$TICK_INPUT" | python3 "$STAGES_DIR/dag/evaluate.py")
DAG_STATE=$(echo "$TICK_OUTPUT" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['state']))")
ACTIONS=$(echo "$TICK_OUTPUT" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['actions'], indent=2))")

echo "Actions: $ACTIONS"
echo ""

# Show current state
echo "Task states after tick 1:"
echo "$DAG_STATE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for tid, t in d['tasks'].items():
    print(f'  {tid}: {t[\"status\"]}')
"
echo ""

# ============================================================
# Phase 5: Simulate agent work — create a PR on Gitea
# ============================================================
echo "--- Phase 5: Simulate Agent Work ---"

# Find the first Ready task
READY_TASK=$(echo "$DAG_STATE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for tid, t in d['tasks'].items():
    if t['status'] == 'Ready':
        print(tid)
        break
")

if [ -z "$READY_TASK" ]; then
    echo "No Ready task found. Something went wrong."
    exit 1
fi

READY_ISSUE=$(echo "$DAG_STATE" | python3 -c "import json,sys; print(json.load(sys.stdin)['tasks']['$READY_TASK']['issue_number'])")
echo "  Working on: $READY_TASK (Issue #$READY_ISSUE)"

# Comment on issue (simulating agent assignment)
gitea_post "/api/v1/repos/$REPO/issues/$READY_ISSUE/comments" \
    "{\"body\": \"@caloron-agent-agent-1 has been assigned this task.\"}" > /dev/null
echo "  Posted assignment comment"

# Simulate: agent opens a PR (just post a comment saying PR opened)
gitea_post "/api/v1/repos/$REPO/issues/$READY_ISSUE/comments" \
    "{\"body\": \"Agent opened PR #999 for this task.\"}" > /dev/null
echo "  Simulated PR opened"
echo ""

# ============================================================
# Phase 6: Simulate PR merge event → run tick
# ============================================================
echo "--- Phase 6: Sprint Tick 2 (PR merge) ---"

# Manually advance to InProgress then InReview
DAG_STATE=$(echo "$DAG_STATE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
d['tasks']['$READY_TASK']['status'] = 'InReview'
d['tasks']['$READY_TASK']['pr_number'] = 999
d['tasks']['$READY_TASK']['started_at'] = '2026-04-08T10:00:00Z'
json.dump(d, sys.stdout)
")

# Simulate a PR merge event
TICK_INPUT=$(cat <<EOF
{"state": $DAG_STATE, "events": [{"type": "pr_merged", "pr_number": 999, "actor": "agent-1", "created_at": "2026-04-08T11:00:00Z"}], "stall_threshold_m": 60}
EOF
)

TICK_OUTPUT=$(echo "$TICK_INPUT" | python3 "$STAGES_DIR/dag/evaluate.py")
DAG_STATE=$(echo "$TICK_OUTPUT" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['state']))")
ACTIONS=$(echo "$TICK_OUTPUT" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['actions'], indent=2))")

echo "Actions: $ACTIONS"
echo ""

echo "Task states after tick 2:"
echo "$DAG_STATE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for tid, t in d['tasks'].items():
    print(f'  {tid}: {t[\"status\"]}')
"
echo ""

# ============================================================
# Phase 7: Check completion
# ============================================================
echo "--- Phase 7: Check Completion ---"

COMPLETE_OUTPUT=$(echo "{\"state\": $DAG_STATE}" | python3 "$STAGES_DIR/dag/is_complete.py")
echo "$COMPLETE_OUTPUT" | python3 -m json.tool
echo ""

# ============================================================
# Phase 8: Complete remaining tasks
# ============================================================
echo "--- Phase 8: Complete All Tasks ---"

# Find all non-Done tasks and complete them one by one
REMAINING=$(echo "$DAG_STATE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for tid, t in d['tasks'].items():
    if t['status'] != 'Done':
        print(tid)
")

for TASK_ID in $REMAINING; do
    # Move to InReview with a fake PR
    DAG_STATE=$(echo "$DAG_STATE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
t = d['tasks']['$TASK_ID']
if t['status'] == 'Ready':
    t['status'] = 'InReview'
    t['pr_number'] = 1000
    t['started_at'] = '2026-04-08T12:00:00Z'
json.dump(d, sys.stdout)
")

    # Merge
    TICK_INPUT="{\"state\": $DAG_STATE, \"events\": [{\"type\": \"pr_merged\", \"pr_number\": 1000, \"actor\": \"agent-2\", \"created_at\": \"2026-04-08T13:00:00Z\"}], \"stall_threshold_m\": 60}"
    TICK_OUTPUT=$(echo "$TICK_INPUT" | python3 "$STAGES_DIR/dag/evaluate.py")
    DAG_STATE=$(echo "$TICK_OUTPUT" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['state']))")
    echo "  $TASK_ID → Done"
done
echo ""

# ============================================================
# Phase 9: Final state + KPIs
# ============================================================
echo "--- Phase 9: Final State ---"

echo "$DAG_STATE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for tid, t in d['tasks'].items():
    print(f'  {tid}: {t[\"status\"]}')
"

COMPLETE_OUTPUT=$(echo "{\"state\": $DAG_STATE}" | python3 "$STAGES_DIR/dag/is_complete.py")
echo ""
echo "Completion check:"
echo "$COMPLETE_OUTPUT" | python3 -m json.tool

# KPIs
echo ""
echo "--- KPIs ---"
KPI_INPUT="{\"state\": $DAG_STATE, \"started_at\": \"2026-04-08T10:00:00Z\", \"ended_at\": \"2026-04-08T14:00:00Z\"}"
echo "$KPI_INPUT" | python3 "$STAGES_DIR/retro/compute_kpis.py" | python3 -m json.tool

# ============================================================
# Phase 10: Verify Gitea issues exist
# ============================================================
echo ""
echo "--- Gitea Issues ---"
ISSUES=$(gitea_get "/api/v1/repos/$REPO/issues?state=open&limit=50")
echo "$ISSUES" | python3 -c "
import json, sys
issues = json.load(sys.stdin)
for i in issues:
    print(f'  #{i[\"number\"]}: {i[\"title\"]} (comments: {i[\"comments\"]})')
"

echo ""
echo "=========================================="
echo " Test Complete!"
echo "=========================================="
