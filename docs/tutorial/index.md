# Tutorial: evolve `citecheck` with an autonomous sprint

You have:

- A CLI (`citecheck`) with structured commands — see the [ACLI tutorial](https://alpibrusl.github.io/acli/tutorial/)
- A composable verification graph — see the [Noether tutorial](https://alpibrusl.github.io/noether/tutorial/)
- A `citation-auditor.agent` that wraps it all — see the [AgentSpec tutorial](https://alpibrusl.github.io/agentspec/tutorial/)

What you don't have: a way to let agents *evolve* `citecheck`. When a user reports "it doesn't handle DOIs", the fix is a sprint of work — design the feature, write code, add tests, open a PR, get it reviewed, merge.

Caloron runs that sprint autonomously. You give it a goal; it produces a merged PR, tests passing, and a retrospective that improves the next sprint.

| Part | Runs without LLM? | Ends with... |
|---|---|---|
| [1. Quick-start](#quick-start) | ✅ | Init a project, navigate its CLI |
| [2. Basic example: run a sprint](#basic-example-run-a-sprint) | ❌ needs LLM runtime | An autonomous sprint that adds DOI support to citecheck |
| [3. Inspecting what happened](#inspecting-what-happened) | ✅ | Metrics, history, agent profiles — all offline |
| [4. Integrate with code assistants](#integrate-with-code-assistants) | ✅ | Assistants can kick off sprints and read retros |
| [5. Where to next](#where-to-next) | — | The other tutorials, and the full ecosystem |

## Quick-start

Install:

```bash
pip install caloron-alpibru
caloron version
```

Caloron pulls `agentspec-alpibru` and `acli-spec` automatically.

Create a project:

```bash
caloron init citecheck-evolution --backend direct
```

Output:

```
Created project: citecheck-evolution
  Path:      /home/you/.caloron/projects/citecheck-evolution
  Backend:   direct
  Framework: claude-code

Now run: caloron sprint "<your goal>"
```

A caloron "project" is a folder under `~/.caloron/projects/` that holds:

- `config.yml` — repo, backend, framework preferences
- `sprints.json` — full history of every sprint you've run (KPIs, retros, agents that participated)
- `profiles/` — signed agent profiles from AgentSpec
- `agents/` — the `.agent` manifests used in each sprint
- `workspace/` — where the actual code-producing sprint runs

Explore the CLI — none of these need an LLM:

```bash
caloron status                  # current project + last sprint summary
caloron projects list           # all projects on this machine
caloron history                 # past sprints in the active project
caloron metrics                 # aggregated KPIs across sprints
caloron agents                  # agent profiles with portfolios
caloron config get framework    # current config
caloron introspect              # full command tree (ACLI)
caloron --help                  # structured help
```

Also works, though currently empty because we haven't run any sprint yet:

```bash
caloron history --output json   # JSON for your own tooling
caloron metrics --output json   # KPIs machine-readable
```

Caloron's design goal is that **everything you might want to inspect is CLI-discoverable without running a sprint.** The "run the sprint" part is where LLM costs happen; "see what happened" is always free.

## Basic example: run a sprint

!!! warning "From here on, you need a runtime"
    Caloron sprints spawn AgentSpec-defined agents, which in turn invoke an LLM CLI. Either:

    - `ANTHROPIC_API_KEY=<key>` for Claude direct
    - `GOOGLE_CLOUD_PROJECT=<proj>` + ADC for Vertex AI (recommended for work use)
    - Any other LLM CLI AgentSpec supports

### The goal

We have `citecheck` (from the ACLI tutorial) verifying Markdown links. A user has asked for DOI support — something like `[Rust paper](doi:10.1145/3453483)` should resolve the DOI and verify the resulting article.

That's our sprint:

```bash
cd ~/citecheck     # the project the sprint will modify

caloron sprint "Add DOI support to citecheck. When a citation URL looks like \
'doi:<id>' or 'https://doi.org/<id>', resolve it via https://api.crossref.org, \
then verify the resulting canonical URL with the existing verify logic. \
Add pytest tests with at least three DOIs (valid article, invalid DOI, \
withdrawn paper). Update the CLI help to document the new behavior. \
Don't modify the existing flow for HTTP URLs."
```

### What caloron does

The sprint runs through these steps; you'll see output in real time:

```
─── Sprint 1 — citecheck-evolution ───

▸ Step 1: PO Agent plans the sprint
  → 3 tasks generated:
    1. add_doi_parser: detect doi: and doi.org URLs, resolve via crossref
    2. wire_doi_verify: plumb the parser into existing verify() flow
    3. add_doi_tests: three pytest cases

▸ Step 2: HR Agent assigns skills and runtime
  → task "add_doi_parser" → claude-code (Vertex AI)
  → task "wire_doi_verify" → claude-code (Vertex AI)
  → task "add_doi_tests" → claude-code (Vertex AI)

▸ Step 3: Agents execute
  [add_doi_parser] writes src/citecheck/doi.py + tests/test_doi.py
    opens PR #1
    reviewer requests changes: "don't rely on doi.org redirects"
    fixes applied
    tests pass, merged ✓
  [wire_doi_verify] modifies src/citecheck/main.py
    opens PR #2
    tests pass, merged ✓
  [add_doi_tests] — subsumed by previous, removed

▸ Step 4: Retro
  Tasks completed: 2/3 (third merged into first)
  Avg clarity: 8.5/10
  Tests passing: 12 (3 new for DOI)
  Supervisor interventions: 0
  Time: 4m 21s

▸ Step 5: Agent profiles updated
  add_doi_parser@1.0.0 → added to portfolio
  wire_doi_verify@1.0.0 → added to portfolio
```

After it finishes, your `citecheck` repo has real commits. You can review them:

```bash
git log --oneline
git diff HEAD~3
pytest tests/
citecheck verify doi:10.1145/3453483 --claim "Rust language"
```

### Why this is different from just asking Claude

A one-shot prompt to Claude ("add DOI support to my Python CLI") might produce similar code. What caloron adds is the **loop**:

1. **Plan before code** — the PO Agent produces a DAG of tasks. If a task looks too big or vague, you see it and can interrupt.
2. **Review cycle** — agents open real PRs; a reviewer agent reads them; the implementer agent fixes; up to N cycles. You end up with code that passed scrutiny, not first-draft code.
3. **Retro → next sprint** — the blockers captured in this sprint ("tests needed mocked HTTP", "DOI format varies more than expected") feed into the next sprint's plan. The agents get smarter about your codebase over time.
4. **Signed trail** — every decision is logged, every agent's contribution goes into its portfolio, all signed by the supervisor. An auditor can reconstruct what happened.

## Inspecting what happened

All of this runs offline — no LLM needed. These commands read the local `~/.caloron/projects/<name>/` directory.

### Status

```bash
caloron status
```

```
Active project: citecheck-evolution
  Backend:   direct
  Framework: claude-code
  Sprints:   1
  Last:      sprint #1 — 2/3 tasks (clarity 8.5/10)
```

### History

```bash
caloron history
```

```
Sprints in citecheck-evolution (1 shown):

  #1  2/3 tasks, clarity 8.5/10  (261s)
      Add DOI support to citecheck. When a citation URL looks like 'doi:<id>'...
```

### Sprint detail

```bash
caloron show 1
```

Full retro for sprint #1: per-task status, blockers encountered, tools used, tests added, final verdict.

### Aggregated metrics

```bash
caloron metrics
```

After one sprint it's sparse. After ten it's where you see trends:

```
Metrics for citecheck-evolution
  Total sprints:       10
  Total tasks:         28
  Completed:           24 (86%)
  Failed:              2
  Avg clarity:         7.8/10
  Avg sprint time:     347s
  Supervisor events:   3

  Most common blockers:
    4× Tests needed mocked HTTP responses
    3× DOI format varies more than expected
    2× Path handling on Windows

  Most used tools:
    28× pytest
    18× httpx
    11× ruff
```

That "most common blockers" section is the highest-signal piece. It tells you where your codebase needs better documentation, better fixtures, or better testing infrastructure. You fix those; next sprint's agents don't hit them.

### Agent profiles

```bash
caloron agents
```

Shows every agent that's ever worked on this project, with its signed portfolio. If an agent has done 8 sprints where DOI handling worked correctly, its `doi-handling` skill is at confidence 0.85. The HR Agent uses this to pick the right agent for the next task in this domain.

```bash
caloron agents add_doi_parser
```

Shows the detailed profile — every memory (retro finding), every portfolio entry (past sprint), every skill with confidence, all signed.

## Integrate with code assistants

Caloron's CLI is ACLI-compliant. An assistant that can run shell commands can kick off sprints and read the retros.

Generate the skill file:

```bash
caloron skill > CALORON_SKILLS.md
```

### Claude Code

```markdown title="CLAUDE.md"
# This project uses Caloron for autonomous sprints

## When to use caloron instead of writing code directly

Use `caloron sprint "<goal>"` when:
- The task will touch multiple files and benefit from a review cycle
- The task is a feature addition with clear acceptance criteria
- You want a signed audit trail (regulated environment)

Do NOT use caloron for:
- Single-line fixes — just edit the file
- Exploratory refactors — code directly, iterate in conversation
- Tasks that need human judgment mid-flight

## Commands

- `caloron status` — what's active
- `caloron history` — past sprints
- `caloron sprint "<goal>"` — run a new autonomous sprint
- `caloron show <id>` — see a past sprint's retro
- `caloron metrics` — aggregated KPIs

See CALORON_SKILLS.md for the full CLI reference.
```

### Cursor

```markdown title=".cursor/rules/caloron.md"
---
description: Caloron sprint orchestration
alwaysApply: false
---

For multi-file feature work, prefer a caloron sprint over direct editing:

    caloron sprint "<goal stated as acceptance criteria>"

When writing goals, be specific about:
- What NOT to change (keep existing behavior for X)
- What tests must pass
- What scope is too big for this sprint (defer to next)

Retrospectives under `~/.caloron/projects/<name>/sprints.json` are the
source of truth for past agent work — read them before planning new sprints.
```

### Copilot / Gemini / Aider / Codex / opencode

Same pattern. Each assistant that can run commands reads `CALORON_SKILLS.md` and knows it can call `caloron` directly.

### The assistant-orchestrates-caloron flow

What you gain when your assistant can invoke caloron:

1. You describe work informally in chat
2. Assistant reformulates it as a clear sprint goal and runs `caloron sprint "..."`
3. The sprint does the actual work with the full loop (plan → code → review → merge → retro)
4. Assistant reads the retro and reports results back to you
5. Next conversation, `caloron history` gives the assistant context about past work

The assistant moves from *coder* to *supervisor of coders*. Humans stay in the loop for the goal and the review, but not the keystrokes.

## Where to next

- **[ACLI tutorial](https://alpibrusl.github.io/acli/tutorial/)** — how `citecheck` became a discoverable CLI in the first place
- **[Noether tutorial](https://alpibrusl.github.io/noether/tutorial/)** — how its internals became composable stages
- **[AgentSpec tutorial](https://alpibrusl.github.io/agentspec/tutorial/)** — how `citation-auditor.agent` wraps the CLI for agents

All four tutorials share the same `citecheck` use case. Caloron is where the loop closes — because now the agents that audit with `citecheck` can also extend `citecheck` itself.

## Further reading

- [Comparison](../comparison.md) — how caloron differs from LangGraph, CrewAI, AutoGen
- `caloron introspect` — the full, machine-readable CLI reference
- `caloron sprint --help` — every flag `caloron sprint` accepts
