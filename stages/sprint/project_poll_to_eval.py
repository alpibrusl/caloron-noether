#!/usr/bin/env python3
"""Reshape: scope-after-poll-binding → dag_evaluate input.

After a ``Let { poll: github_poll_events }``, the body's scope contains
the outer sprint-tick input fields plus ``poll: {events, polled_at}``.
``dag_evaluate`` expects ``{state, events, stall_threshold_m}`` flat at
the top level — this stage builds that record.

Input:
  { state: Any, poll: Record { events: List<Any>, polled_at: Text },
    stall_threshold_m: Number }

Output:
  { state: Any, events: List<Any>, stall_threshold_m: Number }

Effects: [Pure]

Why a typed reshape stage rather than a generic "project": Noether's
type system loses all visibility if reshape is parameterised by a
dynamic mapping. Each boundary reshape gets its own narrow, typed
stage — small Python, but the composition graph remains fully
auditable and dry-run type-checks end-to-end.
"""


def execute(input: dict) -> dict:
    poll = input.get("poll") or {}
    return {
        "state": input["state"],
        "events": poll.get("events", []),
        "stall_threshold_m": int(input.get("stall_threshold_m", 20)),
    }
