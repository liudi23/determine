"""CLI: `determine run "question"` — Phase 0 runs the dry pipeline end-to-end."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from determine.config import load_settings
from determine.corpus.fetch_arxiv import load_corpus
from determine.orchestrate.graph import run_pipeline
from determine.retrieve.bm25 import BM25Retriever


def main() -> None:
    ap = argparse.ArgumentParser(prog="determine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="run the pipeline on a question")
    run_p.add_argument("question")
    run_p.add_argument("--corpus", default=None,
                       help="JSONL corpus path (default: hepph.jsonl if harvested, else sample)")

    report_p = sub.add_parser("report", help="render a run as a readable HTML report")
    report_p.add_argument("run_id", nargs="?", default=None,
                          help="run id (default: latest run)")

    fetch_p = sub.add_parser("fetch", help="harvest hep-ph abstracts from arXiv")
    fetch_p.add_argument("--max-results", type=int, default=5000)
    fetch_p.add_argument("--query", default="cat:hep-ph",
                         help='arXiv query, e.g. \'all:"sterile neutrino" AND cat:hep-ph\'')
    fetch_p.add_argument("--out", default="data/corpus/hepph.jsonl",
                         help="output JSONL (use a topic_*.jsonl then scripts/merge_corpus.py)")

    args = ap.parse_args()
    cfg = load_settings()

    if args.cmd == "report":
        from determine.report import report_run
        out = report_run(cfg.runs_dir, args.run_id)
        print(f"report written: {out}\nopen it with:  open {out}")
        return

    if args.cmd == "fetch":
        from determine.corpus.fetch_arxiv import fetch_hepph
        n = fetch_hepph(query=args.query, max_results=args.max_results, out_path=args.out)
        print(f"harvested {n} abstracts -> {args.out}")
        return

    if args.corpus:
        corpus_path = args.corpus
    else:  # default: the real harvested corpus when present, sample as fallback
        main_corpus = Path(cfg.corpus_dir) / "hepph.jsonl"
        corpus_path = str(main_corpus if main_corpus.exists()
                          else Path(cfg.corpus_dir) / "sample.jsonl")
    corpus = load_corpus(corpus_path) if Path(corpus_path).exists() else []
    print(f"corpus: {corpus_path} ({len(corpus)} abstracts)")
    retriever = BM25Retriever(corpus)
    state = run_pipeline(args.question, cfg, retriever)
    print(json.dumps({
        "run_id": state.run_id, "status": state.status,
        "claims": len(state.claims),
        "score": state.score.model_dump(),
        "persisted": f"{cfg.runs_dir}/{state.run_id}.json",
    }, indent=2))


if __name__ == "__main__":
    main()
