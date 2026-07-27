"""Hallucination-injection test — the primary controlled metric (MVP proposal §4).

Corruptions are pure functions on claims; ground truth is known by construction.
MVP: ~20 injected claims over the 10 demo answers → detection rate + false-alarm rate.
"""

from __future__ import annotations

import random
import re

from determine.schema import Claim


def negate_relation(claim: Claim) -> Claim:
    swaps = [("is consistent with", "is inconsistent with"), ("supports", "contradicts"),
             ("excludes", "allows"), ("confirmed", "refuted"), ("above", "below")]
    text = claim.text
    for a, b in swaps:
        if a in text:
            text = text.replace(a, b, 1)
            break
    else:
        text = "It is not the case that " + text[0].lower() + text[1:]
    return claim.model_copy(update={"text": text})


def perturb_number(claim: Claim, factor: float = 2.0) -> Claim:
    def rep(m: re.Match) -> str:
        return f"{float(m.group()) * factor:g}"
    text, n = re.subn(r"\d+\.?\d*", rep, claim.text, count=1)
    if n == 0:
        raise ValueError("claim has no number to perturb")
    q = claim.quantity.model_copy(update={"value": claim.quantity.value * factor}) \
        if claim.quantity else None
    return claim.model_copy(update={"text": text, "quantity": q})


def swap_entity(claim: Claim, entities: list[str], rng: random.Random) -> Claim:
    for e in entities:
        if e in claim.text:
            others = [o for o in entities if o != e]
            if others:
                return claim.model_copy(update={"text": claim.text.replace(e, rng.choice(others), 1)})
    raise ValueError("no swappable entity found in claim")


def detection_metrics(results: list[tuple[bool, bool]]) -> dict:
    """results: (was_corrupted, was_flagged) per claim → detection + false-alarm rates."""
    corrupted = [f for c, f in results if c]
    clean = [f for c, f in results if not c]
    return {
        "n_corrupted": len(corrupted), "n_clean": len(clean),
        "detection_rate": sum(corrupted) / len(corrupted) if corrupted else None,
        "false_alarm_rate": sum(clean) / len(clean) if clean else None,
    }
