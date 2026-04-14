# Changelog

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
