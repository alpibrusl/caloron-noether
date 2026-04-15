# Changelog

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
