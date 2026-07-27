"""Numeric checker (in MVP) — four check types, everything else declines.

Scope (MVP proposal §6): unit conversions (pint), ratios/percentages, arithmetic
combinations of quoted quantities, tension-in-σ between two values with uncertainties.
Reflect loop hard-capped at 1 critique + 1 fix. Declining (`not_checkable`) is correct
behavior, not failure.
"""

from __future__ import annotations

import math

from determine.config import Settings
from determine.schema import Claim, Computation


def tension_sigma(v1: float, e1: float, v2: float, e2: float) -> float:
    """|v1 - v2| / sqrt(e1² + e2²) — uncorrelated combination, assumption recorded."""
    denom = math.sqrt(e1 * e1 + e2 * e2)
    if denom == 0:
        raise ValueError("zero combined uncertainty")
    return abs(v1 - v2) / denom


def relative_agreement(claimed: float, computed: float, tol: float) -> bool:
    if computed == 0:
        return abs(claimed) <= tol
    return abs(claimed - computed) / abs(computed) <= tol


_NUM = r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?"


def _numbers_in(text: str) -> list[float]:
    import re
    return [float(m) for m in re.findall(_NUM, text)]


def check_claim(claim: Claim, cfg: Settings) -> Claim:
    """Attach a Computation record to a numeric/comparative claim.

    Live v1 (deterministic, LLM-free): compare the claim's structured quantity against
    numbers appearing in the verifier's verbatim evidence quotes, with the configured
    relative tolerance. Anything the comparison can't decide → not_checkable (declining
    is correct behavior). LLM-generated pint/SymPy check scripts are the v2 upgrade.
    """
    if claim.quantity is None or cfg.dry_run:
        claim.computation = Computation(status="not_checkable",
                                        output="declined: no structured quantity or dry-run")
        return claim

    quotes = claim.verdict.quotes if claim.verdict else []
    evidence_numbers = [n for q in quotes for n in _numbers_in(q)]
    if not evidence_numbers:
        claim.computation = Computation(status="not_checkable",
                                        output="declined: no numbers in evidence quotes")
        return claim

    tol = cfg.verdict_tolerance_relative
    claimed = claim.quantity.value
    best = min(evidence_numbers, key=lambda n: abs(n - claimed))
    agrees = relative_agreement(claimed, best, tol)
    claim.computation = Computation(
        status="ok" if agrees else "failed",
        script=f"relative_agreement(claimed={claimed}, evidence={best}, tol={tol})",
        output=f"claimed={claimed} {claim.quantity.unit}; closest evidence number={best}; "
               f"{'within' if agrees else 'OUTSIDE'} {tol:.0%} relative tolerance",
        tolerance_rule=f"relative_{tol:.0%}",
        iterations=1,
    )
    return claim
