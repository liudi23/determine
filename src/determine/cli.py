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
    run_p.add_argument("--corpus", default=None, help="JSONL corpus path (default: sample)")

    fetch_p = sub.add_parser("fetch", help="harvest hep-ph abstracts from arXiv")
    fetch_p.add_argument("--max-results", type=int, default=5000)

    args = ap.parse_args()
    cfg = load_settings()

    if args.cmd == "fetch":
        from determine.corpus.fetch_arxiv import fetch_hepph
        n = fetch_hepph(max_results=args.max_results)
        print(f"harvested {n} abstracts")
        return

    corpus_path = args.corpus or str(Path(cfg.corpus_dir) / "sample.jsonl")
    corpus = load_corpus(corpus_path) if Path(corpus_path).exists() else []
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
