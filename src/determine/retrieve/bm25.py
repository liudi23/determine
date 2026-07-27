"""Deliberately dumb MVP retrieval: BM25 over abstracts.

Hybrid/dense/rerank arrive in the measured Phase-1 comparison, behind this same interface —
which is also the corpus-agnostic handle the verifier receives (MVP proposal §4):
    verify(claim, retriever) -> verdict
"""

from __future__ import annotations

import re
from typing import Protocol

from determine.schema import Passage, span_hash


class Retriever(Protocol):
    def search(self, query: str, k: int = 8) -> list[Passage]: ...


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class _PurePythonBM25:
    """Okapi BM25 fallback (no deps) — used when rank_bm25 isn't installed.

    Same formula and defaults as rank_bm25.BM25Okapi (k1=1.5, b=0.75, floored IDF).
    """

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        import math
        from collections import Counter

        self.k1, self.b = k1, b
        self.docs = docs
        self.doc_len = [len(d) for d in docs]
        self.avgdl = sum(self.doc_len) / len(docs) if docs else 0.0
        self.tf = [Counter(d) for d in docs]
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        # rank_bm25-style IDF with negative-IDF flooring
        idf = {t: math.log((n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        neg = [v for v in idf.values() if v < 0]
        eps = 0.25 * (sum(idf.values()) / len(idf)) if neg and idf else 0.0
        self.idf = {t: (v if v >= 0 else eps) for t, v in idf.items()}

    def get_scores(self, query: list[str]) -> list[float]:
        scores = []
        for i in range(len(self.docs)):
            s, dl = 0.0, self.doc_len[i]
            for t in query:
                if t not in self.tf[i]:
                    continue
                f = self.tf[i][t]
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores.append(s)
        return scores


class BM25Retriever:
    def __init__(self, corpus: list[dict]):
        self.corpus = corpus
        self._docs = [_tokenize(f"{d['title']} {d['abstract']}") for d in corpus]
        if not corpus:
            self._bm25 = None
        else:
            try:
                from rank_bm25 import BM25Okapi
                self._bm25 = BM25Okapi(self._docs)
            except ImportError:
                self._bm25 = _PurePythonBM25(self._docs)

    def search(self, query: str, k: int = 8) -> list[Passage]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        out = []
        for i in ranked:
            d = self.corpus[i]
            text = d["abstract"]
            out.append(Passage(
                passage_id=f"{d['paper_id']}#{span_hash(text)}",
                paper_id=d["paper_id"], text=text, score=float(scores[i]),
            ))
        return out
