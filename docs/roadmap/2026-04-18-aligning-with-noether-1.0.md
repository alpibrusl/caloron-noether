# Caloron-Noether: Aligning with Noether 1.0

**Status:** Draft · 2026-04-18
**Audience:** primarily the maintainer; secondarily caloron-noether users
who want to follow the upgrade path.

Cross-ref: [`noether/docs/roadmap/2026-04-18-rock-solid-plan.md`](../../../noether/docs/roadmap/2026-04-18-rock-solid-plan.md)

## Starting position

Caloron-noether v0.4.x today:

- ~140 stage JSONs under `stages/`, 10 composition graphs under `compositions/`
- Python CLI (`caloron`), Python stages, Rust axum shell (`caloron-shell`)
- Positioned as **reference application for Noether** (README, 2026-04-18 PR)
- Uses Noether via `cargo install noether-cli noether-scheduler` and `subprocess.run(["noether", "run", ...])`
- Depends on Noether's stage store for stage identity; registers local stages from `./stages/`
- No version pinning against Noether — tracks whatever `noether` is on PATH

The job of this doc is to describe how caloron-noether evolves as Noether
ships the 1.0 roadmap in four milestones: M1 canonical hashing, M2
stability + stage versioning, M3 optimizer + types, M4 curated stdlib.

## Release-cadence alignment

Caloron-noether's minor version tracks Noether's minor version. A Noether
change that's observable to caloron-noether users produces a
caloron-noether release with migration notes.

| Noether | caloron-noether | Main change for caloron |
|---------|-----------------|--------------------------|
| 0.4.x | 0.4.x | Current baseline |
| 0.5.0 (M1: canonical hashing) | 0.5.0 | Composition IDs change; trace migration script |
| 0.6.0 (M2: signature/impl split) | 0.6.0 | Graph refs use signature IDs; Noether bugfixes propagate automatically |
| 0.7.0 (M3: optimizer + types) | 0.7.0 | ~2× sprint-tick speedup; optional polymorphism refactor |
| 1.0.0 | 1.0.0 | Drop pre-1.0 workarounds; pin to `noether-cli>=1.0,<2.0` |

The pattern: **no Noether minor ships without a caloron-noether minor
shipping shortly after**, even if the caloron change is only a CHANGELOG
note. This lets downstream users follow one version matrix, not two.

---

## Per-milestone migration notes

### Noether 0.4.x → 0.5.0 · M1 Canonical hashing

**What changes for caloron-noether.** Every composition ID currently
stored in `~/.caloron/kv/*` and in sprint-tick traces is invalidated —
same graph, different bytes. `noether trace <old_id>` returns "not found"
against a v0.5 store.

**Migration, ordered.**

1. On caloron-noether 0.4.x, before the upgrade, run:
   ```bash
   caloron history --format json > ~/.caloron/pre-upgrade-traces.json
   ```
2. Upgrade both Noether and caloron-noether.
3. Run the provided migration command:
   ```bash
   caloron migrate traces ~/.caloron/pre-upgrade-traces.json
   ```
   This re-hashes each composition ID using the canonical form algorithm
   from Noether 0.5 and rewrites the trace store in place. Idempotent.
4. Verify old sprints are still listable:
   ```bash
   caloron history --limit 20
   caloron show 5   # pick any prior sprint; trace should render
   ```
5. Keep `pre-upgrade-traces.json` for at least one caloron-noether minor
   release as a rollback option.

**What improves.**

- Two `sprint_tick_stateful` runs on the same agents/sprint config now
  share a composition ID — deduplication in trace storage, and easier
  diffing between ticks that changed vs ticks that didn't.
- Sprint replay is deterministic across Noether patch versions within 0.5.x.

**What can wait.** No graph rewrites needed at this milestone. Graph
semantics are unchanged; only the hash is canonicalised.

**Test plan.**

- `pytest tests/test_sprint_chain_integration.py` passes before and after
  migration
- Spot-check that `caloron show <N>` produces bit-identical reports for
  N that existed before the migration

---

### Noether 0.5.0 → 0.6.0 · M2 Signature/impl split + stability contract

**What changes for caloron-noether.** Stage references in graph JSON
files now use the **signature** ID, not the full `StageId`. The signature
ID is stable across Noether stdlib bugfixes; the implementation ID is
stored alongside for debuggability and bit-reproducibility. Graphs that
need bit-reproducibility opt in with `"pinning": "both"`.

**Migration, ordered.**

1. Run the one-shot graph rewrite:
   ```bash
   caloron upgrade graphs
   ```
   Rewrites `compositions/*.json` and any graphs under `agents/*/graphs/`
   to use signature IDs. Produces a diff the maintainer reviews before
   committing.
2. Re-run the sprint integration golden tests. The graphs should be
   semantically identical and all tests pass:
   ```bash
   pytest tests/test_sprint_chain_integration.py
   pytest tests/test_sprint_reshape_stages.py
   ```
3. If you need bit-reproducible sprint outputs (e.g., for audit / compliance),
   add `"pinning": "both"` to the top of each production graph. For most
   deployments, the default signature pinning is the right call — Noether
   stdlib bugfixes flow in automatically.
4. Update `CALORON_KV_DIR` schema if you've pinned old implementation IDs
   in stored state; the auto-migration handles the common cases.

**What improves.**

- Noether stdlib bugfixes propagate to caloron-noether users without a
  caloron release — the common case becomes "just upgrade Noether."
- When a stage misbehaves, `caloron show <N>` now displays both signature
  and implementation IDs — easier to correlate a bug to a specific stdlib
  version.

**What can wait.** Adopting `properties` (Noether M2's other feature) on
caloron-specific stages is worth doing but not blocking. Add properties
incrementally as stages drift.

**Test plan.**

- Introduce an intentionally buggy patched stdlib stage, verify
  caloron-noether picks up the fix without any caloron-side change (the
  intent of the split)
- Verify `"pinning": "both"` actually refuses to run against a drifted
  implementation

---

### Noether 0.6.0 → 0.7.0 · M3 Optimizer + richer types

**What changes for caloron-noether.** Performance improves via Pure-stage
fusion and optional memoisation. The type system additions
(parametric polymorphism, row polymorphism, refinement types) are
opt-in — existing stages keep working unchanged.

**Migration, ordered.**

1. Upgrade Noether, re-run the existing stage catalogue registration
   (`./register_stages.sh`) to pick up optimiser compatibility flags.
2. Benchmark `caloron sprint` against a synthetic 5-task DAG fixture.
   Expect ~2× improvement on sprint-tick wall time; if you see regression,
   file a Noether bug with the specific composition — optimiser law
   violations are Noether bugs, not caloron bugs.
3. **Optional refactor.** Consolidate the `stages/dag/*` catalogue using
   parametric polymorphism:
   - Today: `dag_evaluate_unblock`, `dag_evaluate_done`, `dag_is_complete` —
     each hardcodes the task status enum
   - After: `dag_evaluate<S: TaskStatus>`, one stage instead of three
   Estimated 3–5 days, cuts stage count meaningfully, improves
   discoverability. Not urgent; schedule for the next slack week.

**What improves.**

- Sprint-tick wall time drops on any composition that chains multiple
  Pure stages (which most of the retro + DAG eval graphs do)
- The stage catalogue can be consolidated without losing expressiveness

**What can wait.** Refinement types on caloron-specific fields
(e.g., `confidence: Number where 0 <= x <= 1`) are a nice-to-have but
only worth doing where a bug has bitten us.

**Test plan.**

- Benchmark before/after on the full test_sprint_chain_integration suite;
  expect no test fails, faster wall time
- If you refactor `dag_*` stages to polymorphism, add a property-based
  test that any supported `TaskStatus` round-trips through the polymorphic
  stage

---

### Noether 0.7.0 → 1.0.0 · Stability contract adopted

**What changes for caloron-noether.** Nothing functional — that's the
point. Noether 1.x promises binary-compatible stage signatures,
additive-only graph schema, frozen operator semantics. Caloron-noether
can pin `noether-cli >= 1.0, < 2.0` and stay current across all 1.x
Noether patches.

**Migration, ordered.**

1. Bump `pyproject.toml`:
   ```toml
   dependencies = [
     "noether-cli>=1.0,<2.0",
     ...
   ]
   ```
2. Remove migration scripts from prior upgrades that are now dead code
   (`caloron migrate traces`, `caloron upgrade graphs`). Keep as
   deprecation shims for one minor release, then delete.
3. Update `SECURITY.md` to reference Noether 1.0's stability contract
   explicitly: caloron-noether inherits the same contract for any
   caloron-published graph or stage.
4. Bump caloron-noether to 1.0.0 in the same window.

**What improves.**

- Maintenance cost drops: future Noether patch releases don't require
  caloron-noether work for most users.
- Downstream caloron users get the same version-compatibility promise.

---

## Stage catalogue hygiene during Noether M4

Noether M4's curated-stdlib push is the right moment to decide which
caloron stages belong in the Noether stdlib versus staying local.

### Candidates for stdlib promotion

These are generic enough to be useful outside sprint orchestration:

- `dag/evaluate.py` — generic task-DAG status advancement
- `dag/is_complete.py` — DAG completion predicate
- `dag/validate.py` — cycle detection, orphan detection
- `dag/unblocked_tasks.py` — topological frontier extraction

### Keep local to caloron-noether

Sprint-specific or caloron-runtime-specific:

- `supervisor/*` — sprint health heuristics tuned to caloron's agent model
- `retro/*` — sprint retro semantics, caloron-specific KPI set
- `kickoff/*` — ties directly to Gitea / GitHub API shape caloron uses
- `phases/*` — PO / review / reshape logic

### Promotion procedure (per stage)

When promoting a stage to Noether stdlib:

1. Add ≥3 `properties` (required for stdlib per M4 criteria)
2. Extend `examples` from the current count to ≥5
3. Rename to match `{domain}_{verb}_{noun}` convention:
   - `dag/evaluate.py` → `dag_evaluate_unblock` (stdlib name)
   - `dag/is_complete.py` → `dag_check_complete`
4. Submit to Noether stdlib registry review
5. In caloron-noether, replace the local reference with a stdlib-qualified
   reference and mark the local copy deprecated with a `successor` pointer
6. Remove the local copy in the next caloron-noether minor after the
   stdlib stage ships in Noether

### Deprecation signalling

Caloron-local stages that are being superseded by stdlib equivalents get
an explicit `deprecated` marker in their JSON:

```json
{
  "name": "dag_evaluate_local",
  "deprecated": {
    "successor": "stdlib:dag_evaluate_unblock",
    "remove_in": "caloron-noether 1.0",
    "reason": "generic task-DAG logic promoted to Noether stdlib"
  },
  ...
}
```

`caloron` warns loudly when a sprint uses a deprecated stage, pointing at
the successor.

---

## Posture for caloron-noether at Noether 1.0

When Noether hits 1.0, caloron-noether has three plausible futures.
Pick one before the 1.0 release; don't ship ambiguous.

### Posture A — Reference application (recommended)

- README already says this (2026-04-18 positioning pass).
- Stays at 1.x, tracks Noether 1.x, tutorials stay current.
- No aggressive feature work. Every PR earns its place against "does this
  make Noether's story clearer?"
- Low-effort maintenance; high-leverage for Noether's adoption story.

**What this requires going forward:**
- A monthly sanity-check CI run against `noether-cli` main branch to
  catch API drift early
- Accept that some feature requests will be closed as "out of scope for
  a reference app"

### Posture B — Framework for others to fork

- Extract what's generic (DAG + agent dispatch + retro) into
  `caloron-lib`, a reusable library.
- `caloron-noether` itself becomes a thin opinionated layer on top.
- Forks inherit the library, pick their own opinions.

**What this requires:**
- Non-trivial refactoring (split sprint-specific from generic)
- API surface commitment for the library portion — needs its own
  stability contract
- Active maintenance of the library portion even when caloron-noether is
  quiet

### Posture C — Supported product

- Real agent-orchestration product with SLAs, UI, billing.
- Probably in a different repo (`alpibrusl/caloron-cloud`?) or a
  separately-maintained fork.
- Not compatible with "reference app" framing; pick one or the other.

**What this requires:**
- A business case independent of Noether — caloron-noether must win on
  its own, not as noether marketing
- Funding or hiring, because this is a 2+-person project

**Recommendation from the 2026-04-17 audit: A.** This doc assumes A; if
you decide to go B or C, rewrite the next edition.

---

## Rollback strategy

For each Noether minor bump that affects caloron-noether:

- Keep the prior caloron-noether tag deployable for at least **two minor
  versions** of caloron-noether after the bump
- `pip install caloron-alpibru==<prior>` with the matching `noether-cli`
  must work, so a user bitten by a regression can pin back
- Migration scripts (`caloron migrate traces`, `caloron upgrade graphs`)
  stay in the repo for two minor versions, then move to a maintenance
  directory `caloron/migrations/archive/`

---

## Known gaps in this plan

These need attention before or during M1:

- **No CI job rebuilding caloron-noether against Noether main.** Adds
  one `.github/workflows/noether-main-compat.yml` running weekly, opens
  an issue if it fails.
- **No published compatibility matrix** (which noether-cli versions
  pair with which caloron-noether versions). Add to README once Noether
  0.5 ships.
- **No formal stage-catalogue version alongside caloron-noether version.**
  Right now `stage_catalog.py` changes are silent. Either bump
  caloron-noether's minor on any `stage_catalog.py` semantic change, or
  introduce a `CATALOG_VERSION` constant exposed via `caloron introspect`.

Fix during M2 alongside the signature/impl split — the timing is
natural, since that's where caloron's compatibility promises formalise.

---

## Success criteria for this alignment doc

This doc works if, 12 months from now:

- Caloron-noether's version map matches Noether's without drift
- No user has been silently broken by a Noether release
- Stage catalogue hygiene has graduated 4 stages to stdlib cleanly
- caloron-noether 1.0 ships alongside Noether 1.0 with the "reference
  app" framing intact

If it doesn't work, the failure shape is: caloron-noether lags Noether
minors, stdlib promotion never happens, users get conflicting versions.
Catch that at each milestone's review, don't wait for it to show up at 1.0.
