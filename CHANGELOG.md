# Changelog

## 0.4.2 (2026-04-16)

Threads ``host`` through sprint_tick_stateful so the v0.4.1
GitHub-or-Gitea targeting actually reaches the downstream stages.

### Fixed

- ``load_tick_state`` now accepts and passes through a ``host`` field;
  sprint_tick_stateful's required input is now
  ``{sprint_id, repo, stall_threshold_m, token_env, shell_url, host}``
  (6 fields, was 5). Setting ``host`` to a Gitea API root e.g.
  ``http://172.17.0.2:3000/api/v1`` makes every downstream github_*
  stage in the composition target that backend instead of GitHub.
  Default empty string preserves pre-0.4.2 behaviour (api.github.com).

  Without this fix the v0.4.1 ``host`` parameter only reached
  callers that invoked github_* stages directly — sprint_tick_stateful
  would have ignored it because load_tick_state didn't forward it.

### Tests

- 2 new tests on load_tick_state covering host pass-through and the
  empty-string default. 269/269 suite green.

### How to run sprint_tick_stateful against local Gitea

Now that the wiring is complete, the full invocation:

```bash
export PATH="$HOME/.cargo/bin:$PATH"
export GITEA_TOKEN=...
export CALORON_KV_DIR=/tmp/caloron-pilot-kv

# Find the gitea container's bridge IP for direct host access:
GITEA_IP=$(docker network inspect bridge \
  | python3 -c 'import json,sys; d=json.load(sys.stdin)[0];
print([c["IPv4Address"].split("/")[0] for c in d["Containers"].values()
       if "gitea" in c.get("Name","")][0])')

noether run compositions/sprint_tick_stateful.json --input \
  "{\"sprint_id\": \"pilot\", \"repo\": \"caloron/full-loop\",
    \"stall_threshold_m\": 20, \"token_env\": \"GITEA_TOKEN\",
    \"shell_url\": \"http://localhost:7710\",
    \"host\": \"http://${GITEA_IP}:3000/api/v1\"}"
```

The composition still hasn't been live-validated end-to-end against a
real Gitea container from a permissive environment — that's the next
field-pilot opportunity.

## 0.4.1 (2026-04-16)

Hot follow-up to v0.4.0 from the live-validation pilot: surfaced a real
architectural gap and shipped the unblocking fix. The pilot itself
hit a sandbox network limitation that prevented end-to-end completion;
documented below.

### Fixed

- **github_* stages no longer hardcode `api.github.com`.** Pilot
  finding: caloron's actual production usage is Gitea-based (via
  `orchestrator.py:gitea()` using `docker exec` against a local
  container), but the composition stages all hardcoded `api.github.com`
  — meaning sprint_tick_stateful.json type-checked but couldn't drive
  caloron's real Gitea loop. This was why no field user was running
  the new composition path despite v0.4.0 shipping it.

  Each of the seven affected stages now accepts a `host` input field
  with a default of `https://api.github.com`. Set to your Gitea API
  root (e.g. `http://172.17.0.2:3000/api/v1` for a local container,
  or `https://gitea.example.com/api/v1` for hosted) to target a
  self-hosted forge. Both backends expose the same `/repos/<owner>/
  <repo>/...` endpoints, so one stage covers both.

  Stages updated:
  - github_poll_events, github_create_issue, github_post_comment,
    github_add_label, github_merge_pr, get_pr_status,
    fetch_repo_context.

  Catalogue (stage_catalog.py) updated to declare the `host` field
  in each input schema; re-registers cleanly against Noether v0.3.1.

### Added

- 16 unit tests under `tests/test_github_host_param.py` covering:
  - default-host fallback (api.github.com still works)
  - explicit host substitution via captured-URL assertions
  - trailing-slash robustness
  - per-stage smoke (one test per affected stage)
  - catalogue-vs-source consistency check (stage source accepts
    `host` ↔ catalogue declares it; catches drift)

### Known limitation: pilot incomplete in this session

The original pilot goal — "run sprint_tick_stateful end-to-end against
local Gitea via noether-scheduler" — couldn't complete because the
sandboxed shell environment can't reach the docker bridge IP
(`172.17.0.2:3000`). Both `curl` and the noether-stage-runner timed
out trying to reach Gitea from outside the container.

To complete the live pilot in a permissive environment:

```bash
export PATH="$HOME/.cargo/bin:$PATH"
export GITEA_TOKEN=...      # your Gitea API token
export CALORON_KV_DIR=/tmp/caloron-pilot-kv

# Edit compositions/sprint_tick_stateful.json's input shape to include host,
# OR pass via the --input JSON. The host needs to be reachable from wherever
# `noether run` actually executes — for a local Gitea container, the bridge
# IP is reliable: docker network inspect bridge | grep IPv4
noether run compositions/sprint_tick_stateful.json --input \
  '{"sprint_id": "pilot", "repo": "caloron/full-loop",
    "stall_threshold_m": 20, "token_env": "GITEA_TOKEN",
    "shell_url": "http://localhost:7710",
    "host": "http://172.17.0.2:3000/api/v1"}'
```

Note: sprint_tick_stateful's current input schema doesn't declare
`host` — it'd need to be threaded through `load_tick_state` and on to
the github_* stages. Tracked as the next composition refinement; not
shipped in 0.4.1 because the architectural enabler (the host param)
is what was actually missing.

### Scope notes

- The composition wiring for `host` (threading it through
  load_tick_state into the inlined sprint_tick_core) is straightforward
  but not in this release. Adds two lines to `load_tick_state.py`'s
  output schema and one input field to the catalogue. Will batch with
  the conventions-as-tools work in a future release.
- No field reports yet on whether anyone's exercising the github
  stages directly (vs. composing them via sprint_tick_*). If you are,
  the new `host` parameter is opt-in — leaving it unset preserves
  pre-0.4.1 behaviour exactly.

## 0.4.0 (2026-04-16)

Major: the sprint-tick loop is Noether-native now. Plus testability
infrastructure for the remaining blind spots.

### Added

- **`sprint_tick_core.json`** — pure Noether composition for one
  pass of the per-minute sprint tick. Uses nested `Let` bindings with
  typed reshape stages at each boundary, so each domain stage
  (`github_poll_events`, `dag_evaluate`, `check_agent_health`,
  `decide_intervention`, `execute_actions`) keeps its minimal input
  contract while the composition threads data between them. End-to-end
  type-checks against Noether v0.3.1 in 8 steps.
- **`sprint_tick_stateful.json`** — KV-wrapped variant that reads
  persisted state before the tick and writes it after, so
  noether-scheduler can drive caloron end-to-end across reboots. State
  lives under `$CALORON_KV_DIR` (default `~/.caloron/kv/`), one JSON
  file per sprint namespaced by `sprint_id`. Scheduler input is just
  `{sprint_id, repo, stall_threshold_m, token_env, shell_url}` —
  everything else (state, agents, interventions, since) comes from
  disk.
- **Seven reshape / KV stages** under `stages/sprint/` implementing
  the composition: `project_poll_to_eval`,
  `project_health_to_intervention`, `project_all_to_execute`,
  `build_tick_output`, `load_tick_state`, `save_tick_state`. All
  declared in `stage_catalog.py` and registered by
  `register_stages.sh` alongside the legacy 20.
- **Stub agent framework** (`orchestrator/orchestrator.py` +
  `scripts/stub_agent.py`) — a deterministic fixture-driven framework
  entry replayable from JSON. Unlocks end-to-end integration tests
  that drive `orchestrator.main()` without a live LLM, closing the
  "mystery mid-sprint behaviour" blind spot flagged in v0.3.1.

### Fixed

- **Deprecated the original `sprint_tick.json`** — its stage-ID
  references hadn't been valid since Noether v0.3's hash scheme
  changed. Kept in place with a `_deprecated` marker pointing at the
  replacement until docs and demo cast files are updated; will be
  deleted in v0.5.

### Tests

- 12 unit tests on the new KV-persistence stages (cold-start
  defaults, atomic writes, per-sprint isolation, malformed-file
  tolerance, caller-override precedence, save→load round-trip).
- 8 unit/integration tests on the stub framework (registry entry,
  argv construction, PO returns DAG, reviewer returns APPROVED,
  agent feedback envelope parseable, fixture missing/corrupt
  handling).
- 7 tests on the sprint-tick reshape stages (shape conversion
  correctness, default handling for first-tick case).

Total: **251 tests green** (up from 200 in v0.3.3). Lint clean.

### Scope notes

- `sprint_tick_stateful.json` uses caloron's own KV directory rather
  than Noether's built-in KV stages. Two reasons: matches
  orchestrator.py's existing file-based state model (learnings.json,
  etc.), and avoids requiring Noether KV to be wired into every
  caloron deployment. A Noether-KV variant is straightforward if
  needed later (swap the two stages).
- The stub framework is not a replacement for real sprints — it
  produces whatever the fixture dictates and has no reasoning. Its
  job is deterministic regression coverage of the sprint loop wiring,
  not sprint quality.

## 0.3.3 (2026-04-15)

Closes the "advisory only" gap in agent skill resolution that has been
the root cause of mystery tool-use failures in field reports.

### Added

- **`required_skills` on PO tasks.** Each task can now declare a list
  of skills/tools the resolved agent MUST have. Before execution, the
  orchestrator validates declared requirements against what the
  resolver actually matched (union of HR-agent skills, tools_used,
  and `agentspec.tools`). Tasks with missing skills are blocked with
  a diagnostic record rather than run with a silently-weaker agent.
  Sprint aborts (exit 3) when every task is blocked; continues with
  the runnable subset otherwise, surfacing blocked tasks as retro
  blockers. The PO prompt teaches this schema explicitly.
- **Loud warning when agentspec isn't installed.** The HR-agent
  keyword-matching fallback is strictly weaker than agentspec's
  manifest resolver and produces correctly-shaped but incorrectly-
  tooled tasks. The warning is now a multi-line stderr block with
  `pip install agentspec-alpibru` instructions and the explicit
  `CALORON_ALLOW_NO_AGENTSPEC=1` escape hatch for intentional
  fallback (minimal CI environments).

### Tests

- 9 unit tests covering resolved-skill union logic, case-insensitive
  matching, blocked-task reporting, and mixed-batch splits.
- 116/116 suite green.

### Notes on what's still advisory

`agentspec.missing_tools` remains advisory and is NOT wired into the
blocker flow — it's about *resolution* completeness, while
`required_skills` is about *task contract*. Conflating them would be a
design mistake. A future release may add a `required_mcps` or
`required_auth` field on the same pattern if field reports demand it.

## 0.3.2 (2026-04-15)

Adds a house-style conventions layer so teams with a standard way of
laying out projects, naming packages, licensing files, etc. don't have
to re-teach every agent every sprint.

### Added

- **`caloron.organisation` module** — loads YAML conventions from
  `$CALORON_HOME/organisation.yml` (global) and
  `<project>/caloron.yml` (project-level override, right-wins merge).
  Schema covers `organisation`, `package_naming`, `imports`,
  `repository_layout`, `license`, `dependencies`, `commit_message`,
  `branch_naming`; unknown sections pass through to an "Other" bucket
  so nothing is silently dropped. Malformed YAML surfaces as a warning
  — sprints never crash on a bad config.

- **`caloron org` subcommand group**:
  - `caloron org init` — scaffold a template at
    `$CALORON_HOME/organisation.yml` with sensible defaults and
    comments describing each section. Refuses to overwrite.
  - `caloron org show [--project DIR]` — render the prompt block
    agents will see. Supports `--output json` for scripting.
  - `caloron org validate` — load + parse, exit non-zero on warnings.

- **Conventions propagation**. `caloron sprint` now loads conventions
  (project override + global), renders them into a markdown block,
  and passes via `CALORON_CONVENTIONS` env var to the orchestrator.
  The orchestrator appends the block to:
  - the PO prompt (so task decomposition respects house style),
  - per-task agent prompts (so implementation follows the rules),
  - the reviewer prompt (so review checks include convention
    compliance),
  - the fix prompt (so regression fixes don't re-introduce
    violations).
  Empty conventions → env var unset → no empty headers added,
  preserving prompt-cache friendliness.

### Notes

- Conventions are **injected into agent context**, not enforced at
  tool level. An agent that ignores the rules will still merge; the
  reviewer is the backstop. Tool-level enforcement (ruff configs,
  pre-commit hooks, CI gates shaped by the same YAML) is the next
  layer — tracked for a later release.
- Skills / tools / MCP enforcement in the existing `agentspec_bridge`
  remains advisory (tracked via `missing_tools` / warnings; never
  aborts the sprint). This release does not change that — it's
  orthogonal to the conventions work.

### Tests

- 15 unit tests on the loader + renderer (empty defaults, missing
  file, malformed YAML, non-mapping top-level, project override
  wins, roundtrip).
- 4 CLI smoke tests on `caloron org {init,show,validate}`.
- 2 new integration tests proving the conventions block ends up in
  the PO subprocess argv when `CALORON_CONVENTIONS` is set, and
  does NOT appear when unset. 107/107 suite green.

## 0.3.1 (2026-04-15)

Second-round field-report fixes on top of v0.3.0. po_context propagation
and the other v0.3.0 items were confirmed working in production; the
remaining three issues are about PO intelligence rather than broken
plumbing — addressed here.

### Fixed

- **PO prompt timed out around sprint 5-6**. A field report hit 9-minute
  PO generation at sprint 3 with only 300s headroom. Two-part fix:
  - ``build_po_context`` now uses a two-tier compression: the most
    recent 2 sprints get full blocker lists; everything before that
    folds into an aggregate (total tasks, completion rate, recurring
    blocker themes surfaced at ≥2 occurrences). Prompt size stops
    growing linearly with sprint count.
  - ``--po-timeout auto`` / ``PO_TIMEOUT=auto`` scales with sprint
    count: 300s base + 60s per prior sprint, capped at 900s. Users
    who don't want the cap can still pass an explicit integer.
- **PO decomposed implementation goals into test tasks**. When the
  sprint goal enumerated specific fixes, the PO kept producing the
  generic "impl + tests" two-task split, which was the #1 source of
  wasted cycles in the field report. Prompt rewritten to read the
  goal's structure: if it enumerates N items, generate N tasks tied
  to those items; classify intent (implement / test-only / refactor)
  before deciding what shape of task to emit. "Keep to 2-3 tasks"
  removed. Worked examples cover both bug-fix and test-coverage goals.
- **FastAPI scaffold triggered on CLI projects**. Generic keywords
  like ``api`` and ``endpoint`` were enough to pick the FastAPI
  template for any goal that happened to mention APIs — including
  CLI tools consuming an external API. Keywords tightened to
  specific phrases (``fastapi``, ``rest api``, ``http endpoint``,
  ``web service``). New ``anti_keywords`` template field penalises
  (-3) web scaffolds when the goal signals CLI shape (``cli``,
  ``argparse``, ``click``, ``command-line``). Both the Python
  built-in templates and the YAML user-facing templates updated.

### Added

- ``anti_keywords`` field on templates (built-in + YAML) to encode
  "this template should lose when the goal signals a different
  project shape."
- ``auto_po_timeout(sprint_count)`` helper + ``PO_TIMEOUT=auto`` env
  value + ``--po-timeout auto`` CLI value for dynamic scaling.
- Context-compression test coverage (``build_po_context`` with 5
  sprints asserts older ones are folded into aggregates; recurring
  themes section appears when blockers repeat; auto-timeout scales
  and caps correctly).
- Scaffold-selection test coverage (CLI goals don't pick FastAPI;
  FastAPI goals still pick FastAPI; "mentions API" in a CLI goal
  doesn't trigger FastAPI).

### Carried-forward from 0.3.0 (confirmed working in field)

po_context propagation, reviewer framework inheritance, Gitea
preflight, --debug / --po-timeout / --skip-gitea-check flags, broader
CLAUDE.md scope, force-merge escalation — all verified in production
per the field report.

## 0.3.0 (2026-04-15)

Addresses seven issues surfaced by two field reports from teams running
multi-sprint projects with caloron-noether v0.1–0.2.

### Fixed

- **`po_context` silently empty in sprint 2+** (critical). The PO agent
  read learnings from disk but several downstream consumers — and the
  retro itself — had no visibility into whether context actually
  propagated. `build_po_context` now covers the last 3 sprints instead
  of just the last one, surfaces force-merged tasks explicitly, and
  carries forward cumulative improvements. The loaded context size is
  printed on sprint start, and the generated context is persisted back
  into `learnings.json` as `last_po_context` for post-hoc inspection.
  Without this fix the "learning" system didn't actually learn.
- **Reviewer agent hardcoded to claude-code**. Same class of bug as
  #2 (fixed in v0.2.0) but in a different code path: the reviewer and
  fixer subprocess calls defaulted to `claude-code` even when the
  project was configured for gemini-cli / codex-cli / etc., so the
  entire review cycle was wasted with "Not logged in" stderr output.
  `run_agent_with_supervision` now inherits the project's FRAMEWORK
  by default; callers can still override per task.
- **PO agent timeout hardcoded at 120s**. As sprint context grew
  (accumulated learnings, long specs), the PO timed out mid-generation
  around sprint 4 — users had to patch inside the installed pip
  package. Now configurable via `--po-timeout` (CLI) or `PO_TIMEOUT`
  env var; default raised to 300s.
- **Gitea dependency undocumented + silent when absent**. Sprints used
  to "complete" with fake issue numbers, fake PR numbers, and no real
  version control when no Gitea container was running. A preflight
  check now verifies the container is up and the API responds; if not,
  the sprint aborts with a clear error and a docker-compose snippet.
  Bypass with `--skip-gitea-check` (or `CALORON_SKIP_GITEA_CHECK=1`).
- **Force-merge indistinguishable from approval**. PRs force-merged
  after the 3-cycle review cap used to record only "Force merged after
  3 cycles" in blockers, which blended into the noise. They now get a
  `⚠️ FORCE-MERGED …unresolved: {last review feedback}` prefix so the
  next sprint's `build_po_context` can surface them separately as
  technical debt to address.
- **`CLAUDE.md` scope too narrow**. Scaffolded instructions said "only
  create/modify files in src/ and tests/" but real tasks routinely
  need `pyproject.toml`, `config/`, `Dockerfile`, etc. — this was the
  top blocker in both reporter's second sprint. Instructions now
  explicitly allow project-level files; the upload filter was widened
  correspondingly. Caloron-managed paths (`.caloron/`, `.mcp.json`,
  generated `CLAUDE.md`, etc.) remain protected.

### Added

- **`--debug` flag on `caloron sprint`**. Dumps the full PO prompt
  (goal + learnings context + instructions) to stderr before
  execution. Makes prompt bloat and timeout issues diagnosable without
  patching inside the installed package.
- **`--po-timeout` flag on `caloron sprint`** mirroring `PO_TIMEOUT`
  env var.
- **`--skip-gitea-check` flag on `caloron sprint`** for CI / dev
  environments that intentionally run without version control.

### Documentation

- Gitea is now documented as a required runtime dependency with a
  one-line `docker run` snippet. Non-claude frameworks continue to
  carry the experimental/lower-fidelity caveat from v0.2.0.

## 0.2.0 (2026-04-14)

### Fixed

- **Packaging** (#1): `scripts/sandbox-agent.sh` was missing from the pip
  wheel, so `caloron sprint` crashed on a fresh `pip install`. The wheel
  now bundles `scripts/` under `caloron/_scripts/` via hatch
  `force-include`.
- **macOS support** (#1): `sandbox-agent.sh` uses `bwrap` and is
  Linux-only. Added `sandbox-passthrough.sh` (no-op fallback) and runtime
  auto-selection in the CLI: honours `$SANDBOX` → picks `bwrap` on Linux
  when available → otherwise uses the passthrough. Override with
  `SANDBOX=/path/to/your-sandbox.sh`.
- **Framework propagation** (#2): the PO, HR, and reviewer agents plus
  per-task defaults were hardcoded to `claude-code`, so
  `caloron init --framework X` silently ran under Claude. The CLI now
  exports `CALORON_FRAMEWORK` and the orchestrator threads it through to
  every agent invocation and prompt template.
- **Non-Claude frameworks** (#3): each CLI was launched in one-shot Q&A
  mode with no file/shell tools, producing plans but no code. Updated
  invocation flags:
  - `gemini-cli`: add `-y` (yolo / auto-approve tool calls)
  - `aider`: `--yes-always` (was the wrong `--yes`)
  - `codex-cli`: migrate to `codex exec --full-auto <prompt>` (upstream
    removed `--approval-mode`)
  - `open-code`: fix latent empty-arg bug in `build_agent_command`
  - `cursor-cli`: new entry using `cursor-agent -p --output-format text`

### Added

- `caloron sprint` prints a single-line note to stderr when the selected
  framework is not `claude-code`, pointing at the tracking issue if the
  CLI isn't authenticated.

## 0.1.0 (2026-04-08)

Initial release.

- 16 Python stages: DAG, GitHub, supervisor, retro, kickoff
- 4 composition graphs: sprint_tick, kickoff, retro, spawn_agent
- Thin Rust shell (~200 lines): heartbeat, spawn, status endpoints
- Stage registration script
- Scheduler configuration
- Side-by-side comparison test against Gitea
- MkDocs documentation (14 pages)
