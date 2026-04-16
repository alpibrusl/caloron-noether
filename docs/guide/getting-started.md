# Getting Started

Two paths, depending on what you want to do.

## Path A — Run a real sprint (production)

This is what every field user actually does. The Python orchestrator
(`caloron sprint`) drives the full loop against a Gitea container and
your authenticated coding-agent CLI.

### Prerequisites

- **Python 3.11+**
- **Docker** (for the Gitea container)
- **An authenticated coding agent on `$PATH`** — `claude`, `gemini`,
  `cursor-agent`, `opencode`, `aider`, or `codex`. Best-tested by far
  is `claude` (Pro/Max subscription or `ANTHROPIC_API_KEY`); other
  frameworks are wired but not yet field-validated.

### Install + start Gitea

```bash
pip install caloron-alpibru

# Start a local Gitea container if you don't already have one:
docker run -d --name gitea -p 3000:3000 -p 222:22 gitea/gitea:1.22

# Create a token at http://localhost:3000/-/user/settings/applications
# and either set GITEA_TOKEN or accept the dev-mode default (caloron's
# orchestrator carries one for local development).
```

### Run a sprint

```bash
caloron init my-project --framework claude-code
caloron sprint "Build a Python module with is_palindrome. Include tests."
caloron status
```

The orchestrator handles: PO planning → agent spawning under sandbox →
PR creation in Gitea → reviewer cycle → merge → retro → learnings
persisted for the next sprint. Hooked into `caloron metrics`,
`caloron history`, etc.

### Optional: organisation conventions

```bash
caloron org init           # writes ~/.caloron/organisation.yml
caloron org show           # preview the prompt block agents will see
```

Edit the YAML to declare your house style (package naming, license
headers, dependency policy). Every sprint will inject those rules into
the PO, agent, and reviewer prompts. See
[organisation.yml schema](https://github.com/alpibrusl/caloron-noether/blob/main/caloron/organisation.py).

## Path B — Run a Noether composition (the new path)

If you want to drive sprints via Noether compositions (and eventually
`noether-scheduler` on a cron), you also need Noether installed:

```bash
cargo install noether-cli noether-scheduler
# or grab prebuilt binaries from
# https://github.com/alpibrusl/noether/releases/latest

# (Optional) point at the hosted stage registry
export NOETHER_REGISTRY=https://registry.alpibru.com

# Register caloron's stages with the local Noether store
./register_stages.sh         # the ~20 domain stages
./register_phases.sh         # the architect/dev/review phase chain (writes
                             # compositions/full_cycle_resolved.json)
```

### Run the phase pipeline

```bash
noether run compositions/full_cycle_resolved.json --input '{
  "goal": "Build a HealthCheck and a LoggingAdapter.",
  "constraints": "Python 3.11+, no external deps."
}'
```

Output is a typed `{tasks: [...]}` list — the same shape `caloron
sprint --graph <path>` consumes when you want sprint planning to run
through the composition rather than the built-in PO.

### Run a per-tick sprint loop

```bash
GITEA_TOKEN=... \
GITEA_IP=$(docker network inspect bridge | python3 -c '
import json, sys; d=json.load(sys.stdin)[0];
print([c["IPv4Address"].split("/")[0] for c in d["Containers"].values()
       if "gitea" in c.get("Name","")][0])')

noether run compositions/sprint_tick_stateful.json --input "{
  \"sprint_id\": \"pilot\",
  \"repo\": \"caloron/full-loop\",
  \"stall_threshold_m\": 20,
  \"token_env\": \"GITEA_TOKEN\",
  \"shell_url\": \"http://localhost:7710\",
  \"host\": \"http://${GITEA_IP}:3000/api/v1\"
}"
```

`host` was added in v0.4.1/v0.4.2 so the github stages can target a
self-hosted Gitea — leave it empty to hit `api.github.com` instead.

State persists between ticks under `$CALORON_KV_DIR`
(default `~/.caloron/kv/<sprint_id>.json`). Run noether-scheduler
against `scheduler.json` to make this fire on a cron.

## Next steps

- [Architecture](architecture.md) — what runs where, current diagram
- [Stage Catalog](../reference/stage-catalog.md) — full I/O signatures
  for every stage
- [Compositions](compositions.md) — the working composition graphs and
  what each one does
