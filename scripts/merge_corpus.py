"""Merge all data/corpus/*.jsonl files into hepph.jsonl, deduplicated by paper_id.

Run:  python scripts/merge_corpus.py
Keeps the main corpus versioned and free of duplicates after targeted topic fetches.
"""

from __future__ import annotations

import json
from pathlib import Path

CORPUS_DIR = Path("data/corpus")
MAIN = CORPUS_DIR / "hepph.jsonl"


def main() -> None:
    seen: dict[str, dict] = {}
    sources = sorted(CORPUS_DIR.glob("*.jsonl"))
    for path in sources:
        if path.name == "sample.jsonl":
            continue
        with path.open() as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    seen.setdefault(rec["paper_id"], rec)
    with MAIN.open("w") as f:
        for rec in seen.values():
            f.write(json.dumps(rec) + "\n")
    print(f"merged {len(sources)} file(s) -> {MAIN} ({len(seen)} unique papers)")


if __name__ == "__main__":
    main()
