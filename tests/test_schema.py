import pytest

from determine.schema import (
    Claim,
    ClaimType,
    NEIReason,
    RunState,
    Verdict,
    VerdictLabel,
)


def test_nei_requires_reason():
    with pytest.raises(ValueError):
        Verdict(label=VerdictLabel.NEI)
    v = Verdict(label=VerdictLabel.NEI, reason=NEIReason.NO_EVIDENCE)
    assert v.reason == NEIReason.NO_EVIDENCE


def test_reason_only_for_nei():
    with pytest.raises(ValueError):
        Verdict(label=VerdictLabel.SUPPORTED, reason=NEIReason.CONFLICT)


def test_verdict_totality_enforced():
    state = RunState(question="q")
    state.claims = [Claim(text="c1", type=ClaimType.REPORT)]
    with pytest.raises(AssertionError):
        state.assert_verdict_totality()
    state.claims[0].verdict = Verdict(label=VerdictLabel.SUPPORTED, quotes=["x"], passage_ids=["p"])
    state.assert_verdict_totality()


def test_strict_score():
    state = RunState(question="q")
    for label, kw in [(VerdictLabel.SUPPORTED, {}), (VerdictLabel.SUPPORTED, {}),
                      (VerdictLabel.REFUTED, {}),
                      (VerdictLabel.NEI, {"reason": NEIReason.CONFLICT})]:
        c = Claim(text="c", type=ClaimType.REPORT)
        c.verdict = Verdict(label=label, **kw)
        state.claims.append(c)
    s = state.compute_score()
    assert (s.supported, s.refuted, s.nei) == (2, 1, 1)
    assert s.headline == 0.5  # strict: supported / total, NEI still costs score
