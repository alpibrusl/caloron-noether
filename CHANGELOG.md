# Changelog

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
