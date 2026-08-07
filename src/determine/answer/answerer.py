"""Live grounded answerer — cite-or-abstain contract over retrieved passages."""

from __future__ import annotations

from determine.config import Settings
from determine.llm.client import LLM, extract_json
from determine.retrieve.bm25 import Retriever
from determine.schema import Answer, Passage, RunState

SYSTEM = """You are the answerer of Determine, a scientific claim-verification agent.
Write a concise answer to the question using ONLY the numbered evidence passages provided.
The cite-or-abstain contract:
- Every sentence must be supported by at least one provided passage and must cite it.
- Do NOT use knowledge that is not in the passages, even if you believe it is true.
- If the passages cannot support an answer to some aspect, say so explicitly
  ("The provided literature does not establish ...") — abstention is correct behavior.
- Preserve hedges: if a passage says "suggests", your sentence says "suggests".
- 3-8 sentences total.

Return ONLY JSON:
{"sentences": [{"text": str, "cites": [str]}]}
where "cites" contains the passage ids (given in brackets) supporting that sentence.
A sentence that is pure abstention ("the literature does not establish X") may have empty cites.
ALWAYS return the JSON object, even when the passages cannot answer the question at all —
in that case the abstention statements ARE the sentences. Never reply in plain prose."""


def gather_passages(state: RunState, retriever: Retriever, cfg: Settings) -> dict[str, Passage]:
    """Union of passages for the plan's retrieval seeds (deduplicated; cache-cheap)."""
    out: dict[str, Passage] = {}
    for step in state.plan:
        for seed in step.retrieval_seeds[:2]:
            for p in retriever.search(seed, k=cfg.top_k_passages):
                out.setdefault(p.passage_id, p)
    return out


def answer_live(state: RunState, cfg: Settings, retriever: Retriever, llm: LLM) -> RunState:
    passages = gather_passages(state, retriever, cfg)
    if not passages:
        state.answer = Answer(text="NOT ENOUGH EVIDENCE: no relevant passages were "
                                   "retrieved from the corpus for this question.",
                              sentence_citations={})
        return state
    block = "\n\n".join(f"[{p.passage_id}] {p.text}" for p in list(passages.values())[:16])
    user_msg = f"Question: {state.question}\n\nEvidence passages:\n{block}"
    raw = llm.complete(SYSTEM, user_msg, max_tokens=4000)
    try:
        data = extract_json(raw)
    except ValueError:
        # model answered in prose (often while abstaining) — one retry with feedback
        raw2 = llm.complete(
            SYSTEM,
            user_msg + '\n\nREMINDER: respond ONLY with the JSON object '
                       '{"sentences": [...]}. If the passages cannot answer the question, '
                       "put your abstention statement(s) in 'sentences' with empty cites — "
                       "never plain prose.",
            max_tokens=4000)
        try:
            data = extract_json(raw2)
        except ValueError:
            # honest degradation: keep the prose as an uncited answer; downstream
            # decomposition/verification will treat its claims strictly
            state.answer = Answer(text=raw.strip(), sentence_citations={})
            return state
    sentences = data["sentences"]
    valid_ids = set(passages)
    text = " ".join(s["text"] for s in sentences)
    cites = {i: [c for c in s.get("cites", []) if c in valid_ids]
             for i, s in enumerate(sentences)}
    state.answer = Answer(text=text, sentence_citations=cites)
    return state
