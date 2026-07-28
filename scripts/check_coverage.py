"""Corpus coverage check: BM25 top hits for each demo question.

Run:  python scripts/check_coverage.py [corpus.jsonl]
Prints the top-3 retrieved titles per demo question so you can eyeball whether the
corpus can actually support answering it. No LLM calls, zero cost.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from determine.corpus.fetch_arxiv import load_corpus  # noqa: E402
from determine.retrieve.bm25 import BM25Retriever  # noqa: E402


def demo_questions() -> list[str]:
    text = (Path(__file__).parent.parent / "questions" / "demo_questions.md").read_text()
    return [m.group(1).strip() for m in re.finditer(r"^\d+\.\s+(.*?)\s*\(", text, re.M)]


def main() -> None:
    corpus_path = sys.argv[1] if len(sys.argv) > 1 else "data/corpus/hepph.jsonl"
    corpus = load_corpus(corpus_path)
    print(f"corpus: {corpus_path} — {len(corpus)} abstracts")
    by_id = {d["paper_id"]: d for d in corpus}
    retriever = BM25Retriever(corpus)

    weak = 0
    for q in demo_questions():
        hits = retriever.search(q, k=3)
        print(f"\nQ: {q}")
        if not hits or hits[0].score <= 0:
            print("   !! NO HITS — corpus cannot support this question")
            weak += 1
            continue
        for p in hits:
            d = by_id[p.paper_id]
            print(f"   {p.score:6.2f}  [{d.get('year')}] {d['title'][:90]}")
    print(f"\n{weak} question(s) with no usable hits. "
          "Low/irrelevant top hits => top up the corpus with a targeted fetch:\n"
          '  determine fetch --query \'all:"sterile neutrino" AND cat:hep-ph\' '
          "--out data/corpus/topic_sterile.jsonl --max-results 300\n"
          "  python scripts/merge_corpus.py")


if __name__ == "__main__":
    main()
