# End-to-End Sprint Example

This walkthrough runs a complete sprint using the Python stages against a local Gitea instance.

## The Scenario

Add two features to a web API:
1. `/health` endpoint (no dependencies)
2. `/metrics` endpoint (depends on health)

## Run It

```bash
bash test/compare_sprint.sh
```

## What Happens

```
Phase 1: generate_dag.py decomposes the brief into 2 tasks
Phase 2: validate.py confirms no cycles
Phase 3: create_issue.py creates Gitea issues #1 and #2
Phase 4: evaluate.py unblocks task-1 (no deps) → Ready
Phase 5: Agent assignment comment posted on Gitea
Phase 6: PR merge event → evaluate.py marks task-1 Done, unblocks task-2
Phase 7: is_complete.py: 1/2 done
Phase 8: task-2 completed
Phase 9: is_complete.py: 2/2 done ✓
KPIs: 100% completion, 0 interventions
```

## Output

```
Sprint: sprint-compare-1775679766
Repo: caloron/test-project (Gitea)

Task states after final tick:
  task-1: Done
  task-2: Done

KPIs:
  completion_rate: 1.0
  total_tasks: 2
  completed_tasks: 2
  avg_interventions: 0.0
```
