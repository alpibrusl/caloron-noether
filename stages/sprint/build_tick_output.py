#!/usr/bin/env python3
"""Terminal reshape: accumulated sprint-tick scope → rich tick-result record.

sprint_tick_core's raw execute_actions output is ``{actions_taken, errors}``
— useful for logging but insufficient for state persistence across ticks.
This stage pulls the forward-carry fields from the accumulated Let scope
so the composition's output has everything a caller needs to persist
(via KV, external store, or another composition) before the next tick.

Input:
  { execute_result: Record { actions_taken: List<Text>, errors: List<Text> },
    eval: Record { state: Any, actions: List<Any> },
    poll: Record { events: List<Any>, polled_at: Text },
    supervisor: Record { actions: List<Any>, updated_interventions: Any } }

Output:
  { actions_taken: List<Text>, errors: List<Text>,
    state: Any, polled_at: Text, interventions: Any }

Effects: [Pure]
"""


def execute(input: dict) -> dict:
    execute_result = input.get("execute_result") or {}
    eval_result = input.get("eval") or {}
    poll_result = input.get("poll") or {}
    supervisor = input.get("supervisor") or {}
    return {
        "actions_taken": execute_result.get("actions_taken", []),
        "errors": execute_result.get("errors", []),
        "state": eval_result.get("state", {}),
        "polled_at": poll_result.get("polled_at", ""),
        "interventions": supervisor.get("updated_interventions", {}),
    }
