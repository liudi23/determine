"""Pure-code verification guards — deterministic, LLM-free, unit-tested.

These are the cheap structural defenses fixed in the MVP proposal §2:
a SUPPORTED/REFUTED verdict must quote verbatim from a cited passage.
"""

from __future__ import annotations

from determine.schema import Passage, Verdict, VerdictLabel


def quote_substring_check(verdict: Verdict, passages: dict[str, Passage]) -> list[str]:
    """Return a list of violations (empty = pass).

    Rule: every quote must be a verbatim substring of one of the verdict's cited passages;
    SUPPORTED/REFUTED require at least one quote and one cited passage.
    """
    violations: list[str] = []
    if verdict.label in (VerdictLabel.SUPPORTED, VerdictLabel.REFUTED):
        if not verdict.quotes:
            violations.append("SUPPORTED/REFUTED verdict without a quote")
        if not verdict.passage_ids:
            violations.append("SUPPORTED/REFUTED verdict without a cited passage")
    cited_texts = [passages[pid].text for pid in verdict.passage_ids if pid in passages]
    for q in verdict.quotes:
        if not any(q in t for t in cited_texts):
            violations.append(f"quote not a verbatim substring of any cited passage: {q[:60]!r}")
    return violations
