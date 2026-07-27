from determine.schema import NEIReason, Passage, Verdict, VerdictLabel
from determine.verify.guards import quote_substring_check

P = {"p1": Passage(passage_id="p1", paper_id="x", text="The W mass is 80.4 GeV in stub data.")}


def test_verbatim_quote_passes():
    v = Verdict(label=VerdictLabel.SUPPORTED, quotes=["W mass is 80.4 GeV"], passage_ids=["p1"])
    assert quote_substring_check(v, P) == []


def test_fabricated_quote_fails():
    v = Verdict(label=VerdictLabel.SUPPORTED, quotes=["W mass is 91.2 GeV"], passage_ids=["p1"])
    assert quote_substring_check(v, P)


def test_supported_without_quote_fails():
    v = Verdict(label=VerdictLabel.SUPPORTED, passage_ids=["p1"])
    assert quote_substring_check(v, P)


def test_nei_needs_no_quote():
    v = Verdict(label=VerdictLabel.NEI, reason=NEIReason.NO_EVIDENCE)
    assert quote_substring_check(v, P) == []
