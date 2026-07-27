import json
from pathlib import Path

from determine.config import Settings
from determine.corpus.fetch_arxiv import load_corpus
from determine.orchestrate.graph import run_pipeline
from determine.retrieve.bm25 import BM25Retriever

SAMPLE = Path(__file__).parent.parent / "data" / "corpus" / "sample.jsonl"


def make_cfg(tmp_path) -> Settings:
    return Settings(dry_run=True, runs_dir=str(tmp_path / "runs"))


def test_dry_run_end_to_end(tmp_path):
    cfg = make_cfg(tmp_path)
    retriever = BM25Retriever(load_corpus(str(SAMPLE)))
    state = run_pipeline("What is the W boson mass?", cfg, retriever)

    assert state.status == "complete"
    assert state.plan_review_status == "accepted"
    assert state.claims, "decomposer produced no claims"
    # verdict totality: every claim has a terminal verdict
    state.assert_verdict_totality()
    # numeric claims got a computation record (declined in dry-run is fine)
    numeric = [c for c in state.claims if c.type.value == "numeric"]
    assert all(c.computation is not None for c in numeric)
    # score triple reported
    assert state.score.total == len(state.claims)
    # run state persisted and loadable
    persisted = json.loads((Path(cfg.runs_dir) / f"{state.run_id}.json").read_text())
    assert persisted["run_id"] == state.run_id
    assert persisted["model_per_role"]["verifier"]


def test_empty_corpus_degrades_to_nei(tmp_path):
    cfg = make_cfg(tmp_path)
    state = run_pipeline("Anything", cfg, BM25Retriever([]))
    assert state.status == "complete"
    for c in state.claims:
        assert c.verdict is not None
        assert c.verdict.label.value == "NOT-ENOUGH-EVIDENCE"


def test_injection_metrics():
    from determine.eval.injection import detection_metrics, negate_relation, perturb_number
    from determine.schema import Claim, ClaimType, Quantity

    c = Claim(text="The mass is 80.4 GeV and is consistent with the SM.",
              type=ClaimType.NUMERIC,
              quantity=Quantity(quantity="m", value=80.4, unit="GeV"))
    assert "inconsistent" in negate_relation(c).text
    p = perturb_number(c)
    assert p.quantity.value == 160.8 and "160.8" in p.text
    m = detection_metrics([(True, True), (True, False), (False, False), (False, True)])
    assert m["detection_rate"] == 0.5 and m["false_alarm_rate"] == 0.5
