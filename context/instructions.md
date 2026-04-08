# Caloron-Noether — Implementation Guide

> This document is the complete brief for building `caloron-noether`: a rewrite of the
> Caloron multi-agent orchestration platform where all business logic is expressed as
> Noether composition graphs, and the only native Rust code is a ~300-line process
> spawner + HTTP heartbeat server.

*April 2026*

---

## Table of Contents

1. [What you are building and why](#1-what-you-are-building-and-why)
2. [Prerequisites](#2-prerequisites)
3. [Noether primer — everything you need to know](#3-noether-primer)
4. [Architecture overview](#4-architecture-overview)
5. [Project structure](#5-project-structure)
6. [Stage specifications — what you need to implement](#6-stage-specifications)
7. [Composition graph specifications](#7-composition-graph-specifications)
8. [The thin shell binary](#8-the-thin-shell-binary)
9. [KV state management](#9-kv-state-management)
10. [Scheduler configuration](#10-scheduler-configuration)
11. [Harness protocol — Unix socket → HTTP](#11-harness-protocol)
12. [Implementation order](#12-implementation-order)
13. [Testing each piece](#13-testing)
14. [What changed vs the original Caloron](#14-what-changed-vs-original-caloron)

---

## 1. What you are building and why

The original `caloron` daemon is ~9,300 lines of Rust. About 65% of that code is
business logic (GitHub event handling, DAG evaluation, supervisor decisions, retro
analysis, kickoff flows) expressed as hand-written Rust functions that could instead be
**Noether composition graphs** — typed, content-addressed, effect-tracked pipelines
that run on the Noether execution engine.

`caloron-noether` replaces that logic with:

- **Composition graphs** (JSON) that describe what happens at each step of a sprint tick,
  kickoff, retro, etc.
- **Custom stages** (Python or Rust inline) that implement the non-stdlib logic —
  GitHub API calls, DAG evaluation, health checks.
- **A thin native shell** (~300 lines of Rust) that owns only what Noether cannot do:
  spawning agent worktrees as OS processes, and listening for harness heartbeats over HTTP.
- **`noether-scheduler`** that drives the sprint polling loop — no hand-written event loop.

The result: same capabilities, roughly **6× less code**, and all the logic becomes
type-checked, content-addressed, and reusable across other projects.

---

## 2. Prerequisites

### Installed tools

The Noether CLI and scheduler are built from source. The repo is at
`/home/alpibru/workspace/solv-noether` — you already have it.

```bash
# Build the noether CLI + scheduler (one-time, and after any Noether changes)
cd /home/alpibru/workspace/solv-noether
cargo build --release -p noether-cli

cd /home/alpibru/workspace/noether-cloud
cargo build --release -p caloron-scheduler 2>/dev/null || \
  cargo build --release  # builds all workspace members

# Add both to PATH (add to your shell profile)
export PATH="/home/alpibru/workspace/solv-noether/target/release:$PATH"
export PATH="/home/alpibru/workspace/noether-cloud/target/release:$PATH"

# Verify
noether version
# → { "ok": true, "data": { "version": "0.1.0", ... } }
```

> **No reinstall needed when Noether changes.** Because `caloron-noether` uses path
> dependencies (see §5 for the `Cargo.toml`), `cargo build` inside `caloron-noether`
> always compiles the current state of `solv-noether`. The only time you need to
> re-run the `cargo build --release -p noether-cli` command above is when you want
> the updated `noether` CLI binary for running `noether stage search` or
> `noether run --dry-run` from the terminal.

```bash
# Python 3 (for Python stage implementations)
python3 --version

# Nix (optional but recommended for hermetic Python stages)
nix --version
```

### Environment variables

```bash
# Optional: point at a remote registry (otherwise uses local ~/.noether/store.json)
export NOETHER_REGISTRY=https://your-registry.example.com
export NOETHER_API_KEY=your-key

# Required at runtime
export GITHUB_TOKEN=ghp_...
export OPENAI_API_KEY=sk-...   # or ANTHROPIC_API_KEY / VERTEX_AI credentials
```

### Repository layout

```
workspace/
├── solv-noether/       ← Noether platform (do not modify unless adding stdlib stages)
├── noether-cloud/      ← Registry + scheduler (already hardened)
└── caloron-noether/    ← This project (you are building this)
```

---

## 3. Noether Primer

You need to understand five things. Nothing else is required.

### 3.1 A stage is a typed function

```
stage: { input: T } → { output: U }
identity: SHA-256(implementation + signature)
```

Every stage has a content hash as its ID. Two stages with the same hash are the
same computation — guaranteed. You reference stages by their hash prefix in
composition graphs.

Find a stage's hash:
```bash
noether stage search "spawn a subprocess"
# → { "id": "a1b2c3d4...", "description": "Spawn a subprocess; returns its PID...", ... }

noether stage get a1b2c3d4
# → full stage spec including input/output types
```

### 3.2 A composition graph is JSON

```json
{
  "description": "What this composition does",
  "version": "0.1.0",
  "root": { ... }
}
```

The `root` is a node. There are four node kinds:

```json
{ "op": "Stage", "id": "a1b2c3d4", "_comment": "optional human hint" }

{ "op": "Sequential", "stages": [ <node>, <node>, ... ] }

{ "op": "Parallel", "branches": { "key1": <node>, "key2": <node> } }

{ "op": "Branch",
  "condition": { "op": "Stage", "id": "..." },
  "then": <node>,
  "else": <node> }
```

`Parallel` merges all branch outputs into a single `Record` keyed by branch name.
`Sequential` pipes the output of each node as the input to the next.

### 3.3 Stages declare effects

```
Pure          — deterministic, no side effects, cacheable
Network       — makes HTTP calls
Fallible      — may fail for non-type reasons
Process       — spawns / signals / waits on OS processes  ← new in this version
Llm           — calls a language model
NonDeterministic — same input may produce different outputs
Cost { cents } — has a monetary cost
```

You enforce which effects a composition is allowed to use:
```bash
noether run sprint_tick.json --allow-effects network,fallible,process,llm \
  --input '{"sprint_id": "sprint-42"}'
```

### 3.4 The KV store is your state

Noether has five built-in KV stages backed by SQLite (`~/.noether/kv.db`).
This replaces `DaemonState` from the original Caloron:

```bash
# In a composition graph, use these stage IDs (search to confirm hashes):
noether stage search "Store a JSON value under a key"
noether stage search "Retrieve a JSON value by key"
noether stage search "List all keys"
```

Convention for Caloron keys:
```
caloron:{sprint_id}:state          → DagState JSON
caloron:{sprint_id}:agents         → Map<agent_id, AgentHealth> JSON
caloron:{sprint_id}:last_poll      → ISO timestamp of last GitHub poll
caloron:{sprint_id}:agent:{id}:pid → number, PID of running agent process
```

### 3.5 Running a composition

```bash
# Type-check only (no execution)
noether run --dry-run sprint_tick.json --input '{"sprint_id": "sprint-42"}'

# Execute
noether run sprint_tick.json --input '{"sprint_id": "sprint-42"}'

# With effect restrictions and budget
noether run sprint_tick.json \
  --input '{"sprint_id": "sprint-42"}' \
  --allow-effects network,fallible,process,llm \
  --budget-cents 50
```

Output is always ACLI JSON:
```json
{
  "ok": true,
  "command": "noether",
  "data": { "output": { ... } },
  "meta": { "version": "0.1.0", "composition_id": "...", "effects": [...] }
}
```

---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  noether-scheduler                                               │
│  Runs sprint_tick.json every 60 s                                │
│  Runs kickoff.json on demand                                     │
│  Runs retro.json at sprint close                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │  noether run <graph.json>
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Noether Engine                                                  │
│  ┌────────────────┐  ┌───────────────┐  ┌──────────────────┐   │
│  │  GitHub stages │  │  DAG stages   │  │ Supervisor stages│   │
│  │  (custom)      │  │  (custom Pure)│  │ (custom Pure/LLM)│   │
│  └────────────────┘  └───────────────┘  └──────────────────┘   │
│  ┌────────────────┐  ┌───────────────┐  ┌──────────────────┐   │
│  │  Retro stages  │  │  kv_get/set   │  │  spawn_process   │   │
│  │  (custom LLM)  │  │  (stdlib)     │  │  kill_process    │   │
│  └────────────────┘  └───────────────┘  │  (stdlib ← new!) │   │
│                                         └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                           │  POST /heartbeat (HTTP)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  caloron-shell  (~300 lines Rust)                                │
│  ├─ axum HTTP server:  POST /heartbeat  (replaces Unix socket)  │
│  ├─ POST /spawn    →  fork agent worktree + caloron-harness     │
│  └─ GET  /status   →  list live agent PIDs from KV store        │
└──────────────────────────┬──────────────────────────────────────┘
                           │  stdin/stdout JSON
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Agent processes  (unchanged from original Caloron)              │
│  caloron-harness start                                           │
│  Sends heartbeats to http://localhost:7710/heartbeat             │
└─────────────────────────────────────────────────────────────────┘
```

**Key difference from original Caloron:** the orchestrator loop, all event handling,
health checks, supervisor decisions, retro analysis, and kickoff logic live in
composition graphs. The shell only manages processes and HTTP — nothing else.

---

## 5. Project Structure

```
caloron-noether/
│
├── context/
│   └── instructions.md          ← this file
│
├── stages/                      ← custom stage implementations
│   ├── github/
│   │   ├── poll_events.py       ← fetch events since last_poll
│   │   ├── create_issue.py
│   │   ├── post_comment.py
│   │   ├── get_pr_status.py
│   │   ├── merge_pr.py
│   │   └── add_label.py
│   ├── dag/
│   │   ├── evaluate.py          ← advance task states from events
│   │   ├── unblocked_tasks.py   ← return ready tasks
│   │   └── is_complete.py
│   ├── supervisor/
│   │   ├── check_health.py      ← classify agent from heartbeat log
│   │   ├── decide_intervention.py
│   │   └── compose_message.py   ← LLM: write a helpful GitHub comment
│   ├── retro/
│   │   ├── collect_feedback.py  ← fetch feedback comments
│   │   ├── analyze_feedback.py  ← LLM: themes, insights
│   │   ├── compute_kpis.py      ← Pure: completion rate, velocity
│   │   └── write_report.py      ← LLM: Markdown retro report
│   └── kickoff/
│       ├── fetch_repo_context.py
│       └── generate_dag.py      ← LLM: produce dag.json from brief
│
├── compositions/
│   ├── sprint_tick.json         ← runs every 60s (the main loop)
│   ├── kickoff.json             ← one-shot: start a sprint
│   ├── retro.json               ← one-shot: close a sprint
│   └── spawn_agent.json         ← called by sprint_tick when a task is ready
│
├── shell/
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs              ← CLI: start, status, kickoff, retro
│       ├── spawner.rs           ← fork worktree + harness
│       └── heartbeat_server.rs  ← axum HTTP POST /heartbeat
│
├── scheduler.toml               ← noether-scheduler config
├── Cargo.toml                   ← workspace (shell only)
└── README.md
```

---

## 6. Stage Specifications

Each stage is a Python file. The harness is simple: read JSON from stdin, write JSON
to stdout, exit 0 on success, exit 1 on failure (stderr is captured for error messages).

```python
#!/usr/bin/env python3
import sys, json

input_data = json.load(sys.stdin)
# ... logic ...
json.dump(output_data, sys.stdout)
```

To register a stage with Noether:
```bash
noether stage submit stage-spec.json
```

A stage spec JSON looks like:
```json
{
  "description": "Human-readable description (used as the stage ID in find_implementation)",
  "input": { "type": "Record", "fields": { "field1": "Text", "field2": "Number" } },
  "output": { "type": "Record", "fields": { "result": "Text" } },
  "effects": [{ "effect": "Network" }, { "effect": "Fallible" }],
  "capabilities": ["Network"],
  "implementation": {
    "language": "python3",
    "code": "import sys, json\n..."
  }
}
```

The easiest workflow: write the Python file, embed it in the spec with
`"code": $(python3 stage.py | base64)`, then submit.

---

### 6.1 GitHub stages

All GitHub stages use the `GITHUB_TOKEN` environment variable. They all declare
`effects: [Network, Fallible]` and `capabilities: [Network]`.

---

#### `github_poll_events`

Fetches all GitHub events (new issues, issue comments, PR reviews, label changes)
on the sprint repo since a given timestamp.

```
Input:
  {
    repo:       Text   -- "owner/repo"
    since:      Text   -- ISO 8601 timestamp of last poll
    token_env:  Text   -- env var name holding the GitHub token (default: "GITHUB_TOKEN")
  }

Output:
  {
    events:     List<Record>   -- each event: { type, issue_number, actor, body, label, created_at }
    polled_at:  Text           -- ISO timestamp of this poll (store in KV as last_poll)
  }
```

Events to capture:
- `issue_opened` — new issue with `caloron:task` label
- `issue_comment` — comment on a sprint issue (may contain feedback YAML)
- `pr_opened` — PR opened by an agent (check if title references a task)
- `pr_review_submitted` — review approved / changes-requested
- `label_added` / `label_removed` — label changes on sprint issues

GitHub API calls you need:
```
GET /repos/{owner}/{repo}/issues/events?since={since}
GET /repos/{owner}/{repo}/issues/comments?since={since}
GET /repos/{owner}/{repo}/pulls?state=open&sort=updated&direction=desc
```

---

#### `github_create_issue`

```
Input:
  {
    repo:     Text
    title:    Text
    body:     Text
    labels:   List<Text>   -- e.g. ["caloron:task", "caloron:blocked"]
    token_env: Text
  }

Output:
  {
    issue_number: Number
    url:          Text
  }
```

API: `POST /repos/{owner}/{repo}/issues`

---

#### `github_post_comment`

```
Input:
  {
    repo:         Text
    issue_number: Number
    body:         Text
    token_env:    Text
  }

Output:
  {
    comment_id: Number
    url:        Text
  }
```

API: `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`

---

#### `github_add_label`

```
Input:
  {
    repo:         Text
    issue_number: Number
    label:        Text
    token_env:    Text
  }

Output:
  { ok: Bool }
```

API: `POST /repos/{owner}/{repo}/issues/{issue_number}/labels`

---

#### `github_merge_pr`

```
Input:
  {
    repo:         Text
    pr_number:    Number
    token_env:    Text
  }

Output:
  {
    merged:       Bool
    merge_commit: Text   -- SHA or ""
  }
```

API: `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge`

---

### 6.2 DAG stages

These are **Pure** — no side effects, fully deterministic. They operate on the
`DagState` JSON that lives in the KV store.

---

#### `dag_evaluate`

Advances task states based on a list of GitHub events.

```
Input:
  {
    state:  Record  -- the DagState from KV (see DagState schema below)
    events: List<Record>  -- from github_poll_events output
  }

Output:
  {
    state:    Record    -- updated DagState
    actions:  List<Record>  -- actions to take: { type, task_id, agent_id, ... }
  }
```

**Actions the evaluator can produce:**

| `type` | Meaning |
|--------|---------|
| `spawn_agent` | Task moved to InProgress; need to start an agent |
| `submit_pr_for_review` | Agent completed work; PR needs a review label |
| `merge_pr` | PR was approved; merge and mark task Done |
| `escalate` | Task stalled too long; create escalation issue |
| `mark_done` | Task finished, no further action needed |

**DagState schema:**
```json
{
  "sprint_id": "sprint-42",
  "tasks": {
    "task-001": {
      "id": "task-001",
      "title": "...",
      "status": "Pending | Ready | InProgress | InReview | Done | Blocked | Escalated",
      "depends_on": ["task-000"],
      "agent_id": null,
      "issue_number": null,
      "pr_number": null,
      "started_at": null,
      "completed_at": null
    }
  }
}
```

The evaluator must:
1. For each `InProgress` task: check for a PR opened by the assigned agent → move to `InReview`
2. For each `InReview` task: check for an approved review → produce `merge_pr` action
3. For each `Pending` task: check if all `depends_on` tasks are `Done` → move to `Ready`, produce `spawn_agent`
4. For each `InProgress` task older than `config.stall_threshold_minutes`: produce `escalate`

---

#### `dag_is_complete`

```
Input:  { state: Record }
Output: { complete: Bool, total: Number, done: Number }
```

Pure: count tasks in `Done` status. `complete` is true when `done == total`.

---

### 6.3 Supervisor stages

---

#### `check_agent_health`

```
Input:
  {
    agent_id:          Text
    last_heartbeat_at: Text    -- ISO timestamp, or null if never
    task_started_at:   Text    -- ISO timestamp
    stall_threshold_m: Number  -- minutes without heartbeat = stalled
  }

Output:
  {
    status:        Text   -- "healthy" | "stalled" | "missing" | "unknown"
    minutes_since: Number -- minutes since last heartbeat
  }
```

Pure logic:
- `missing` — `last_heartbeat_at` is null and task_started_at is > 2 minutes ago
- `stalled` — last heartbeat is older than `stall_threshold_m`
- `healthy` — everything else

---

#### `decide_intervention`

```
Input:
  {
    agent_id:        Text
    health_status:   Text     -- from check_agent_health
    intervention_count: Number -- how many times we've already intervened
    max_interventions:  Number -- from config
  }

Output:
  {
    action:  Text   -- "none" | "probe" | "restart" | "escalate"
    reason:  Text
  }
```

Pure decision tree:
- `healthy` → `none`
- `stalled`, count = 0 → `probe` (post a comment asking for status)
- `stalled`, count = 1 → `restart` (kill + re-spawn)
- `stalled`, count >= 2 → `escalate`
- `missing` → `escalate`

---

#### `compose_intervention_message`

```
Input:
  {
    agent_id:     Text
    task_title:   Text
    health_status: Text
    action:       Text
  }

Output:
  { message: Text }
```

**LLM stage** (`effects: [Llm, NonDeterministic]`). Writes a clear, brief GitHub comment
explaining the situation and what is about to happen. Keep it under 150 words.

Example prompt pattern:
```
Agent {agent_id} working on "{task_title}" has status {health_status}.
Planned action: {action}.
Write a concise GitHub issue comment (< 150 words) notifying the team.
```

---

### 6.4 Retro stages

---

#### `collect_sprint_feedback`

```
Input:
  {
    repo:      Text
    sprint_id: Text
    token_env: Text
  }

Output:
  {
    feedback_items: List<Record>
    -- each: { issue_number, author, body, created_at, is_parsed_yaml: Bool, parsed: Record | null }
  }
```

Fetch all comments on sprint issues that contain a `caloron-feedback:` YAML block
(see the original `FeedbackComment::parse_from_comment` in `caloron-types` for the format).

---

#### `compute_sprint_kpis`

```
Input:
  {
    state:      Record   -- final DagState
    started_at: Text     -- sprint start ISO timestamp
    ended_at:   Text     -- sprint end ISO timestamp
  }

Output:
  {
    total_tasks:      Number
    completed_tasks:  Number
    completion_rate:  Number   -- 0.0–1.0
    sprint_days:      Number
    tasks_per_day:    Number
    escalated_count:  Number
    blocked_count:    Number
  }
```

Pure arithmetic. No LLM.

---

#### `analyze_sprint_feedback`

```
Input:
  {
    feedback_items: List<Record>
    kpis:           Record       -- from compute_sprint_kpis
  }

Output:
  {
    themes:       List<Text>
    improvements: List<Text>
    learnings:    List<Text>
    sentiment:    Text   -- "positive" | "mixed" | "negative"
  }
```

**LLM stage.** Summarise feedback into themes, actionable improvements, and learnings.
Keep each list to 3–5 items.

---

#### `write_retro_report`

```
Input:
  {
    sprint_id:   Text
    kpis:        Record
    analysis:    Record   -- from analyze_sprint_feedback
    started_at:  Text
    ended_at:    Text
  }

Output:
  { report_markdown: Text }
```

**LLM stage.** Write a sprint retrospective in Markdown using the standard format:
What went well / What didn't / What to change / KPIs table.

---

### 6.5 Kickoff stages

---

#### `fetch_repo_context`

```
Input:
  {
    repo:      Text
    token_env: Text
  }

Output:
  {
    description:      Text
    open_issues:      Number
    recent_commits:   List<Record>   -- last 5: { sha, message, author, date }
    languages:        Map<Text, Number>
    default_branch:   Text
  }
```

Uses `GET /repos/{owner}/{repo}` + `GET /repos/{owner}/{repo}/commits?per_page=5`.
Effects: `[Network, Fallible]`.

---

#### `generate_sprint_dag`

```
Input:
  {
    brief:        Text   -- problem description from the user/PO
    repo_context: Record -- from fetch_repo_context
    num_agents:   Number -- target parallelism
  }

Output:
  {
    dag: Record   -- valid DagState JSON with tasks, dependencies, agent assignments
  }
```

**LLM stage.** Generate a sprint DAG from the brief and repo context.

The LLM must output valid JSON matching the DagState schema from §6.2. Include a
system prompt that:
1. Describes the DagState schema
2. Explains that `depends_on` must form a DAG (no cycles)
3. Sets `status: "Pending"` for all tasks initially
4. Assigns `agent_id` values as `"agent-1"`, `"agent-2"` etc. up to `num_agents`
5. Keeps each task description to one sentence

Validate the output with `dag_is_complete` (should return `complete: false, done: 0`).

---

## 7. Composition Graph Specifications

### 7.1 `sprint_tick.json` — the main loop

Run every 60 seconds by `noether-scheduler`. This is the replacement for
`Orchestrator::run`.

```
Input:  { sprint_id: Text, repo: Text, stall_threshold_m: Number }
Output: { actions_taken: List<Text>, dag_complete: Bool }
```

Graph:

```json
{
  "description": "Caloron sprint tick — poll GitHub, advance DAG, supervise agents",
  "version": "0.1.0",
  "root": {
    "op": "Sequential",
    "stages": [

      { "op": "Stage", "id": "<kv_get>",
        "_comment": "Load DagState from kv: caloron:{sprint_id}:state" },

      { "op": "Stage", "id": "<kv_get>",
        "_comment": "Load last_poll timestamp from kv: caloron:{sprint_id}:last_poll" },

      { "op": "Stage", "id": "<github_poll_events>",
        "_comment": "Fetch GitHub events since last_poll" },

      { "op": "Stage", "id": "<kv_set>",
        "_comment": "Save polled_at as new last_poll" },

      { "op": "Stage", "id": "<dag_evaluate>",
        "_comment": "Advance task states; produce actions list" },

      { "op": "Stage", "id": "<kv_set>",
        "_comment": "Persist updated DagState" },

      { "op": "Parallel", "branches": {
        "health": {
          "op": "Sequential", "stages": [
            { "op": "Stage", "id": "<kv_get>",
              "_comment": "Load agents map from KV" },
            { "op": "Stage", "id": "<check_agent_health>",
              "_comment": "Classify each agent's health status" },
            { "op": "Stage", "id": "<decide_intervention>",
              "_comment": "Determine action for each unhealthy agent" }
          ]
        },
        "dag_status": {
          "op": "Stage", "id": "<dag_is_complete>",
          "_comment": "Check if sprint is finished"
        }
      }},

      { "op": "Stage", "id": "<execute_actions>",
        "_comment": "Fan out: spawn agents, post comments, merge PRs, escalate" }
    ]
  }
}
```

> **Note on `execute_actions`:** this stage dispatches the `actions` list from
> `dag_evaluate` and the `interventions` from `decide_intervention` into concrete
> Noether sub-calls or HTTP calls to `caloron-shell`. See §8 for the shell API.

---

### 7.2 `kickoff.json` — start a sprint

One-shot. Run manually or triggered by a webhook.

```
Input:  { brief: Text, repo: Text, num_agents: Number }
Output: { sprint_id: Text, dag: Record, issues_created: Number }
```

Graph:

```json
{
  "description": "Caloron sprint kickoff — generate DAG, create GitHub issues",
  "version": "0.1.0",
  "root": {
    "op": "Sequential",
    "stages": [
      { "op": "Stage", "id": "<fetch_repo_context>" },
      { "op": "Stage", "id": "<generate_sprint_dag>" },
      { "op": "Stage", "id": "<kv_set>",
        "_comment": "Save initial DagState" },
      { "op": "Stage", "id": "<github_create_issue>",
        "_comment": "One issue per task — use a map/fanout over tasks list" },
      { "op": "Stage", "id": "<kv_set>",
        "_comment": "Save issue_number mappings back into DagState" }
    ]
  }
}
```

---

### 7.3 `retro.json` — close a sprint

One-shot. Run at sprint completion (when `dag_is_complete` returns true).

```
Input:  { sprint_id: Text, repo: Text }
Output: { report_path: Text }
```

Graph:

```json
{
  "description": "Caloron sprint retro — collect feedback, analyse, write report",
  "version": "0.1.0",
  "root": {
    "op": "Sequential",
    "stages": [
      { "op": "Stage", "id": "<kv_get>",
        "_comment": "Load final DagState" },
      { "op": "Parallel", "branches": {
        "feedback": { "op": "Stage", "id": "<collect_sprint_feedback>" },
        "kpis":     { "op": "Stage", "id": "<compute_sprint_kpis>" }
      }},
      { "op": "Stage", "id": "<analyze_sprint_feedback>" },
      { "op": "Stage", "id": "<write_retro_report>" },
      { "op": "Stage", "id": "<write_file>",
        "_comment": "Write report Markdown to reports/{sprint_id}.md" }
    ]
  }
}
```

---

### 7.4 `spawn_agent.json` — called when a task is ready

Run by `execute_actions` stage when `dag_evaluate` emits a `spawn_agent` action.

```
Input:
  {
    sprint_id:  Text
    task_id:    Text
    agent_id:   Text
    repo:       Text
    worktree_base: Text   -- base path for worktrees (e.g. /workspace)
  }

Output: { pid: Number, started_at: Number }
```

Graph:

```json
{
  "description": "Spawn an agent worktree and harness process for a task",
  "version": "0.1.0",
  "root": {
    "op": "Sequential",
    "stages": [
      { "op": "Stage", "id": "<setup_worktree>",
        "_comment": "Custom stage: git worktree add + set env vars" },
      { "op": "Stage", "id": "<spawn_process>",
        "_comment": "stdlib: spawn caloron-harness start with env" },
      { "op": "Stage", "id": "<kv_set>",
        "_comment": "Store PID at caloron:{sprint_id}:agent:{agent_id}:pid" }
    ]
  }
}
```

---

## 8. The Thin Shell Binary

`caloron-shell` is the only native Rust code you write. It has three responsibilities:

1. **HTTP heartbeat server** — receives `POST /heartbeat` from `caloron-harness` and
   writes the timestamp to KV. Replaces the Unix socket entirely.

2. **Agent spawner endpoint** — `POST /spawn` triggers `noether run spawn_agent.json`.
   The `execute_actions` stage calls this endpoint when a `spawn_agent` action is emitted.

3. **Status endpoint** — `GET /status` reads agent PIDs from KV and checks liveness
   with `kill -0`.

### HTTP API

```
POST /heartbeat
Body: { "agent_id": "agent-1", "sprint_id": "sprint-42", "status": "working", ... }
Response: { "ok": true }
Side effect: kv_set("caloron:{sprint_id}:agent:{agent_id}:last_heartbeat", now_iso())

POST /spawn
Body: { "sprint_id": "...", "task_id": "...", "agent_id": "...", "repo": "...", "worktree_base": "..." }
Response: { "ok": true, "pid": 12345 }
Side effect: runs noether run spawn_agent.json --input <body>

GET /status
Response: { "agents": [ { "agent_id": "agent-1", "pid": 12345, "alive": true, "last_heartbeat": "..." } ] }
```

### Recommended implementation sketch

```rust
// shell/src/main.rs  (~100 lines)
use axum::{routing::{get, post}, Router, Json, extract::State};
use std::sync::Arc;

#[tokio::main]
async fn main() {
    let port = std::env::var("CALORON_SHELL_PORT")
        .unwrap_or("7710".into())
        .parse::<u16>().unwrap();

    let app = Router::new()
        .route("/heartbeat", post(heartbeat))
        .route("/spawn", post(spawn))
        .route("/status", get(status));

    let addr = format!("127.0.0.1:{port}");
    println!("caloron-shell listening on {addr}");
    axum::serve(
        tokio::net::TcpListener::bind(addr).await.unwrap(),
        app,
    ).await.unwrap();
}
```

Heartbeat handler writes to the Noether KV store using the `noether` CLI subprocess
(or by linking `noether-store` as a library dependency — your choice).

### Dependencies

```toml
# shell/Cargo.toml
[dependencies]
axum       = "0.7"
tokio      = { version = "1", features = ["full"] }
serde      = { version = "1", features = ["derive"] }
serde_json = "1"
```

---

## 9. KV State Management

The KV store replaces `DaemonState` entirely. Convention for key namespacing:

| Key | Value | Updated by |
|-----|-------|------------|
| `caloron:{sprint_id}:state` | `DagState` JSON | `dag_evaluate` |
| `caloron:{sprint_id}:last_poll` | ISO timestamp | `github_poll_events` |
| `caloron:{sprint_id}:started_at` | ISO timestamp | kickoff composition |
| `caloron:{sprint_id}:agents` | `Map<id, AgentHealth>` JSON | `check_agent_health` |
| `caloron:{sprint_id}:agent:{id}:pid` | number | `spawn_process` |
| `caloron:{sprint_id}:agent:{id}:last_heartbeat` | ISO timestamp | heartbeat handler |
| `caloron:{sprint_id}:interventions:{id}` | number (count) | `decide_intervention` |

Access from compositions:
```bash
# Get stage IDs for kv operations
noether stage search "Store a JSON value under a key"
noether stage search "Retrieve a JSON value by key"
noether stage search "List all keys in the persistent key-value store"
```

The KV store is at `~/.noether/kv.db` by default. For production, set
`NOETHER_KV_PATH=/var/lib/caloron/kv.db`.

---

## 10. Scheduler Configuration

`noether-scheduler` drives the sprint polling loop. It replaces the
`Orchestrator::run` async loop entirely.

```toml
# scheduler.toml

[[jobs]]
name        = "sprint-tick"
cron        = "* * * * *"         # every minute
graph       = "./compositions/sprint_tick.json"
input_from  = "kv:caloron:active_sprint"   # reads { sprint_id, repo, stall_threshold_m }
on_error    = "log"               # don't stop on single tick failure

[[jobs]]
name        = "health-check"
cron        = "*/5 * * * *"       # every 5 minutes
graph       = "./compositions/health_check.json"
input_from  = "kv:caloron:active_sprint"

[[jobs]]
name        = "retro"
cron        = "0 18 * * 5"        # Fridays at 18:00
graph       = "./compositions/retro.json"
input_from  = "kv:caloron:active_sprint"
enabled     = false               # enable manually at sprint close
```

Start the scheduler:
```bash
noether-scheduler --config scheduler.toml \
  --registry https://your-registry.example.com   # optional
```

Or point at a local store:
```bash
noether-scheduler --config scheduler.toml \
  --store-path ~/.noether/store.json
```

---

## 11. Harness Protocol

The original `caloron-harness` talks to the daemon over a Unix socket
(`/run/caloron/{sprint_id}.sock`). This caused the socket path mismatch bug
(see `context/comments.md §5`).

**The new protocol is plain HTTP.** Change the harness to:

```rust
// In caloron-harness/src/heartbeat.rs — replace socket with HTTP
async fn send_heartbeat(agent_id: &str, sprint_id: &str, status: &str) {
    let shell_url = std::env::var("CALORON_SHELL_URL")
        .unwrap_or("http://localhost:7710".into());

    let client = reqwest::Client::new();
    let _ = client.post(format!("{shell_url}/heartbeat"))
        .json(&serde_json::json!({
            "agent_id": agent_id,
            "sprint_id": sprint_id,
            "status": status
        }))
        .send()
        .await;
}
```

Set `CALORON_SHELL_URL=http://localhost:7710` in the agent environment at spawn time
(the spawner sets this).

This is a one-line change in `caloron-harness`. The rest of the harness stays the same.

---

## 12. Implementation Order

Work in this order. Each step is independently testable.

### Step 1 — Scaffold the project (Day 1)

```bash
mkdir -p caloron-noether/{stages/{github,dag,supervisor,retro,kickoff},compositions,shell/src,context}
cd caloron-noether
git init
cargo new --name caloron-shell shell
```

Write `Cargo.toml` (workspace with `shell/` as the only member).
Write a minimal `shell/src/main.rs` that starts an axum server with placeholder routes.
Verify it compiles.

### Step 2 — DAG stages (Days 2–3)

Start here because they are **Pure** — no network, no LLM, easy to unit test.

1. Write `stages/dag/evaluate.py` and test it against the task state machine rules
2. Write `stages/dag/is_complete.py`
3. Register both with Noether: `noether stage submit dag-evaluate-spec.json`
4. Verify: `noether stage search "advance task states from events"`

### Step 3 — GitHub stages (Days 3–4)

1. Write and register `github_poll_events.py` — test against your dev repo
2. Write and register `github_create_issue.py`, `github_post_comment.py`, `github_add_label.py`
3. Smoke test: `noether run --dry-run` with sample input

### Step 4 — `sprint_tick.json` composition (Day 4)

Wire the stages together into `compositions/sprint_tick.json`.
```bash
noether run --dry-run compositions/sprint_tick.json \
  --input '{"sprint_id": "test-1", "repo": "your/repo", "stall_threshold_m": 30}'
```
The dry-run type-checks the graph without executing anything. Fix type errors before moving on.

### Step 5 — KV integration (Day 5)

Get the KV stage IDs:
```bash
noether stage search "Store a JSON value under a key" | jq '.data.stages[0].id'
noether stage search "Retrieve a JSON value by key" | jq '.data.stages[0].id'
```

Update `sprint_tick.json` to actually load/save DagState from KV. Test a full
tick with pre-seeded KV data:
```bash
# Seed state
noether run --input '{"key": "caloron:test-1:state", "value": {...}}' kv_set_graph.json

# Run a tick
noether run compositions/sprint_tick.json --input '{"sprint_id": "test-1", ...}'
```

### Step 6 — Shell binary (Days 5–6)

Implement the three endpoints in `shell/src/`:
- `POST /heartbeat` — write to KV
- `POST /spawn` — call `noether run spawn_agent.json`
- `GET /status` — read agent PIDs from KV

Test with curl:
```bash
cargo run -p caloron-shell &
curl -X POST http://localhost:7710/heartbeat \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "agent-1", "sprint_id": "test-1", "status": "working"}'
```

### Step 7 — Supervisor stages (Day 6)

1. Write `check_agent_health.py` and `decide_intervention.py` (Pure, easy to test)
2. Write `compose_intervention_message.py` (LLM — test by running it and reading output)
3. Wire into `sprint_tick.json` under the `health` Parallel branch

### Step 8 — `kickoff.json` + `retro.json` (Days 7–8)

1. Write kickoff stages (`fetch_repo_context.py`, `generate_dag.py`)
2. Test `generate_dag.py` standalone: does the LLM produce valid DagState JSON?
3. Build `compositions/kickoff.json`, end-to-end test against a real repo
4. Write retro stages (easiest last — they're read-only)
5. Build `compositions/retro.json`

### Step 9 — Scheduler integration (Day 9)

1. Write `scheduler.toml`
2. Run `noether-scheduler --config scheduler.toml` and watch it execute `sprint_tick.json` every minute
3. Check KV state is advancing correctly
4. Trigger a kickoff manually, verify DAG is created in KV and issues appear on GitHub

### Step 10 — Harness protocol update (Day 9)

Apply the one-line change in `caloron-harness/src/heartbeat.rs` to use HTTP.
Set `CALORON_SHELL_URL=http://localhost:7710` in the spawn environment.
Start a test agent, verify heartbeats arrive at the shell.

---

## 13. Testing

### Unit testing stages

Each Python stage can be tested directly:
```bash
echo '{"repo": "owner/repo", "since": "2026-04-01T00:00:00Z", "token_env": "GITHUB_TOKEN"}' \
  | GITHUB_TOKEN=$GITHUB_TOKEN python3 stages/github/poll_events.py
```

### Type-checking compositions

```bash
noether run --dry-run compositions/sprint_tick.json \
  --input '{"sprint_id": "x", "repo": "owner/repo", "stall_threshold_m": 30}'
```

A dry-run validates the graph structure, all stage IDs exist, and input/output types
chain correctly — without executing a single stage.

### Integration test: full sprint tick

```bash
# 1. Seed KV with a known DagState
# 2. Run one tick
noether run compositions/sprint_tick.json \
  --input '{"sprint_id": "integ-1", "repo": "owner/repo", "stall_threshold_m": 5}' \
  --allow-effects network,fallible,process,llm

# 3. Read KV and verify state advanced
noether run --input '{"key": "caloron:integ-1:state"}' kv_get_graph.json
```

### Effect policy verification

Verify that a composition that should not need LLM doesn't accidentally call it:
```bash
noether run compositions/sprint_tick.json \
  --allow-effects network,fallible,process \
  --input '...'
# Should succeed — if it fails with "effect violation: llm", a stage is miscategorised
```

---

## 14. What Changed vs Original Caloron

| Original `caloron` | `caloron-noether` |
|---|---|
| `daemon/orchestrator.rs` (404 lines) | `compositions/sprint_tick.json` + `noether-scheduler` |
| `daemon/socket.rs` (345 lines) | `shell/src/heartbeat_server.rs` (~50 lines) |
| `daemon/state.rs` (71 lines) | KV store (`kv_get` / `kv_set` stdlib stages) |
| `git/monitor.rs` (680 lines) | `github_poll_events.py` + `dag_evaluate.py` |
| `git/client.rs` (237 lines) | 5 GitHub stages (~50 lines each) |
| `dag/engine.rs` (627 lines) | `dag_evaluate.py` (~150 lines) + `dag_is_complete.py` |
| `retro/` (2,083 lines) | 4 retro stages + `retro.json` (~400 lines total) |
| `supervisor/` (934 lines) | 3 supervisor stages (~150 lines total) |
| `kickoff/` (514 lines) | 2 kickoff stages + `kickoff.json` (~150 lines total) |
| `agent/registry.rs` (450 lines) | `generate_sprint_dag.py` (~80 lines) |
| `nix/generator.rs` (281 lines) | Keep as-is or port to a `generate_nix_shell.py` stage |
| `agent/spawner.rs` + `worktree.rs` (701 lines) | `shell/src/spawner.rs` (~150 lines) + `spawn_agent.json` |
| `main.rs` (433 lines) | `shell/src/main.rs` (~80 lines) |

**Estimated total: ~1,500 lines** of implementation code (stages + shell) vs ~9,300 lines in the original.

### What does NOT change

- `caloron-types` — the shared type definitions can stay as a reference; the Noether
  version uses JSON schemas instead of Rust structs, but the semantics are the same
- `caloron-harness` — only one line changes (socket → HTTP); everything else stays
- The GitHub label taxonomy and feedback YAML format — unchanged
- The `dag.json` / DagState format — same structure, just stored in KV instead of in-memory

---

## Appendix: Finding Stage IDs

When building composition graphs, you need the hash prefix for each stage.

```bash
# Search by capability
noether stage search "Store a JSON value"
noether stage search "Retrieve a JSON value"
noether stage search "List all keys"
noether stage search "Spawn a subprocess"
noether stage search "Poll until a process exits"
noether stage search "Send SIGKILL"
noether stage search "Send a Unix signal"
noether stage search "Make an HTTP GET request"
noether stage search "Make an HTTP POST request"
noether stage search "Write text content to a file"
noether stage search "Extract a value from JSON"
noether stage search "Interpolate variables into a template"

# All return ACLI JSON — extract the id field:
noether stage search "Spawn a subprocess" | jq '.data.stages[0].id'
```

For **custom stages** you register yourself:
```bash
noether stage submit stages/dag/dag-evaluate-spec.json
# → { "ok": true, "data": { "id": "a1b2c3d4..." } }
# Use this ID in your composition graphs
```

---

*Caloron-Noether — the same orchestration platform, at 1/6th the code.*
