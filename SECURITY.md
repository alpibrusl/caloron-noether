# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public issue**
2. Email: security@alpibrusl.dev (or open a private security advisory on GitHub)
3. Include: description, steps to reproduce, potential impact

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Security Considerations

- Agent credentials are injected via temporary files, not environment variables.
- The Noether KV store uses local SQLite — not exposed to the network.
- GitHub tokens should use minimum required scopes (`repo`, `workflow`).
- The shell HTTP server binds to `127.0.0.1` only. This is a barrier to remote
  hosts but **not** a barrier to other local processes (including browser
  extensions and containers sharing the host network namespace).

## Shell HTTP authentication

Release builds of `caloron-shell` refuse to start unless `CALORON_SHELL_TOKEN`
is set to a non-empty value. Every mutating endpoint (`/spawn`, `/heartbeat`,
`/status`) requires the `X-Caloron-Token` request header and rejects mismatches
with HTTP 401. Comparison is constant-time.

Debug builds (`cargo build` without `--release`) log a warning and allow
unauthenticated access when `CALORON_SHELL_TOKEN` is unset, so local test
workflows don't break. Treat debug builds as developer-only.

Every id field accepted at `/spawn` and `/heartbeat` (`agent_id`, `sprint_id`,
`task_id`) is validated against `^[a-z0-9_-]{1,64}$` at the request boundary.
Path traversal, absolute paths, and shell metacharacters are rejected with
HTTP 400 before any filesystem or subprocess call.

## Claude `--dangerously-skip-permissions`

Caloron invokes `claude` to drive agent sprints, phase PO summaries, and
template bootstrap. Passing `--dangerously-skip-permissions` disables
Claude Code's tool-permission prompts, letting the spawned agent read,
write, and execute anything the process can.

Because DAG content drives prompt content, we treat this as equivalent
to running arbitrary commands from the DAG. The flag is **off by
default** and only attached when the operator explicitly opts in:

```sh
export CALORON_ALLOW_DANGEROUS_CLAUDE=1
```

The gate lives in `orchestrator/claude_flags.py` (`dangerous_flags()`),
and every call site that previously hard-coded the flag now reads from
there. Plain boolean-ish values (`1`, `true`, `yes`, `on`) enable it;
anything else leaves it off.
