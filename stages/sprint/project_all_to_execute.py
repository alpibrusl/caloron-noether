#!/usr/bin/env python3
"""Reshape: accumulated sprint-tick scope → execute_actions input.

By the final stage of sprint_tick_core the scope is layered with every
prior Let binding:

  { ...outer,
    poll:       {events, polled_at},
    eval:       {state, actions},
    health:     {results},
    supervisor: {actions, updated_interventions} }

``execute_actions`` needs
``{repo, token_env, shell_url, dag_actions, supervisor_actions, sprint_id}``
— this stage pulls each field from the right nested location.

Input:
  { eval: Record { actions: List<Any> },
    supervisor: Record { actions: List<Any> },
    repo: Text, token_env: Text, shell_url: Text, sprint_id: Text }

Output:
  { repo: Text, token_env: Text, shell_url: Text,
    dag_actions: List<Any>, supervisor_actions: List<Any>,
    sprint_id: Text }

Effects: [Pure]
"""


def execute(input: dict) -> dict:
    eval_result = input.get("eval") or {}
    supervisor = input.get("supervisor") or {}
    return {
        "repo": input["repo"],
        "token_env": input["token_env"],
        "shell_url": input["shell_url"],
        "dag_actions": eval_result.get("actions", []),
        "supervisor_actions": supervisor.get("actions", []),
        "sprint_id": input["sprint_id"],
    }
