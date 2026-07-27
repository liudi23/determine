"""arXiv abstract harvester (Phase-1 corpus builder).

Corpus format: JSONL, one record per paper:
  {"paper_id": "2203.01234", "title": ..., "abstract": ..., "year": 2022, "categories": [...]}

The harvest is one-shot and versioned: raw responses are stored, and the corpus_version
(harvest date + query) is recorded in every run state so evaluations are reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path


def fetch_hepph(query: str = "cat:hep-ph", max_results: int = 5000,
                out_path: str = "data/corpus/hepph.jsonl") -> int:
    """Harvest hep-ph abstracts via the arXiv API (polite rate limits via `arxiv` lib)."""
    import arxiv  # imported lazily so dry-run/test environments don't need it

    client = arxiv.Client(page_size=100, delay_seconds=3)
    search = arxiv.Search(query=query, max_results=max_results,
                          sort_by=arxiv.SortCriterion.SubmittedDate)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w") as f:
        for result in client.results(search):
            rec = {
                "paper_id": result.get_short_id(),
                "title": result.title,
                "abstract": " ".join(result.summary.split()),
                "year": result.published.year if result.published else None,
                "categories": result.categories,
            }
            f.write(json.dumps(rec) + "\n")
            n += 1
    return n


def load_corpus(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]
