#!/usr/bin/env python3
"""Analyze sprint feedback into themes, improvements, and learnings.

Input:
  { feedback_items: List<Record>, kpis: Record }
Output:
  { themes: List<Text>, improvements: List<Text>, learnings: List<Text>, sentiment: Text }

Effects: [Llm, NonDeterministic]

Note: Uses LLM to synthesize feedback. Falls back to rule-based analysis
if no LLM API key is available.
"""


def execute(input: dict) -> dict:
    feedback_items = input.get("feedback_items", [])
    kpis = input.get("kpis", {})

    themes: list[str] = []
    improvements: list[str] = []
    learnings: list[str] = []

    # Extract parsed feedback
    parsed = [
        f["parsed"]
        for f in feedback_items
        if f.get("is_parsed_yaml") and f.get("parsed")
    ]

    if not parsed:
        # No feedback to analyze — return a shaped empty result.
        return {
            "themes": ["No agent feedback was collected during this sprint"],
            "improvements": [
                "Ensure agents post caloron_feedback comments on task completion"
            ],
            "learnings": [],
            "sentiment": "neutral",
        }

    # Rule-based analysis (no LLM needed for structured feedback)

    # Theme 1: Clarity issues
    low_clarity = [p for p in parsed if p.get("task_clarity", 10) < 5]
    if low_clarity:
        themes.append(f"{len(low_clarity)} tasks had low clarity scores (< 5/10)")
        improvements.append(
            "Add more detail to task specifications — include expected "
            "inputs/outputs and acceptance criteria"
        )

    # Theme 2: Blockers
    all_blockers: list[str] = []
    for p in parsed:
        all_blockers.extend(p.get("blockers", []))
    if all_blockers:
        themes.append(
            f"{len(all_blockers)} blockers reported across {len(parsed)} tasks"
        )
        dep_blockers = [
            b for b in all_blockers if "depend" in b.lower() or "dag" in b.lower()
        ]
        tool_blockers = [
            b for b in all_blockers if "tool" in b.lower() or "unavailable" in b.lower()
        ]
        if dep_blockers:
            improvements.append(
                f"Add missing DAG dependencies — {len(dep_blockers)} runtime deps discovered"
            )
        if tool_blockers:
            improvements.append(
                f"Add missing tools to agent definitions — {len(tool_blockers)} tool gaps found"
            )

    # Theme 3: Assessment distribution
    completed = sum(1 for p in parsed if p.get("self_assessment") == "completed")
    failed = sum(
        1 for p in parsed if p.get("self_assessment") in ("failed", "crashed")
    )
    if failed > 0:
        themes.append(f"{failed} tasks failed or crashed out of {len(parsed)}")
        improvements.append(
            "Investigate failed tasks — consider stronger models or clearer specifications"
        )

    # Theme 4: Token efficiency
    tokens = [p.get("tokens_consumed", 0) for p in parsed if p.get("tokens_consumed")]
    if tokens:
        avg = sum(tokens) / len(tokens)
        high = [t for t in tokens if t > avg * 2]
        if high:
            themes.append(
                f"{len(high)} tasks used significantly more tokens than average ({avg:.0f})"
            )

    # Learnings
    if kpis.get("completion_rate", 0) >= 0.8:
        learnings.append(
            "Sprint had a healthy completion rate — task scoping was appropriate"
        )
    if kpis.get("avg_interventions", 0) > 1:
        learnings.append(
            "High intervention rate — agents may need better prompts or more context"
        )
    if completed == len(parsed):
        learnings.append(
            "All tasks completed successfully — ready to increase sprint scope"
        )

    # Sentiment
    if failed > len(parsed) * 0.3:
        sentiment = "negative"
    elif low_clarity or failed > 0:
        sentiment = "mixed"
    else:
        sentiment = "positive"

    return {
        "themes": themes or ["Sprint completed without notable issues"],
        "improvements": improvements or ["No specific improvements identified"],
        "learnings": learnings or ["Continue with current approach"],
        "sentiment": sentiment,
    }
