"""Live blind verifier — different model family, fresh retrieval, quote guard, budgets.

Independence by construction: this module receives ONLY the bare claim and a retriever.
It never sees the answer, the answerer's citations, or the notebook.
"""

from __future__ import annotations

from determine.config import Settings
from determine.llm.client import LLM, extract_json
from determine.retrieve.bm25 import Retriever
from determine.schema import Claim, NEIReason, Passage, Verdict, VerdictLabel
from determine.verify.guards import quote_substring_check

SYSTEM = """You are an independent scientific fact-checker. You receive ONE claim and a set
of evidence passages retrieved from the peer-reviewed literature. Judge the claim strictly
against these passages — not against your own knowledge.

Labels:
- "SUPPORTED": the passages entail the claim. You MUST copy a verbatim quote (an exact
  substring of one passage) that supports it, and give that passage's id.
- "REFUTED": the passages contradict the claim. Same quote requirement.
- "NOT-ENOUGH-EVIDENCE": the passages neither entail nor contradict the claim
  (reason "no_evidence"), or different passages genuinely conflict (reason "conflict" —
  then provide both quotes in "quote" separated by " ||| ").

Be strict: partial topical overlap is NOT support. Numbers must actually match.

Return ONLY JSON:
{"label": "SUPPORTED" | "REFUTED" | "NOT-ENOUGH-EVIDENCE",
 "quote": str | null, "passage_id": str | null,
 "reason": "no_evidence" | "conflict" | null,
 "confidence": "low" | "medium" | "high"}"""

REFORM_SYSTEM = """You reformulate literature-search queries. Given a scientific claim whose
first search returned no decisive evidence, produce ONE alternative keyword query (different
angle: synonyms, experiment names, observable names). Return ONLY JSON: {"query": str}"""


def _judge(claim: Claim, passages: dict[str, Passage], llm: LLM, cfg: Settings) -> Verdict:
    block = "\n\n".join(f"[{pid}] {p.text}" for pid, p in passages.items())
    raw = llm.complete(SYSTEM, f"Claim: {claim.text}\n\nEvidence passages:\n{block}",
                       max_tokens=1000)
    data = extract_json(raw)
    label = VerdictLabel(data["label"])
    quotes = []
    if data.get("quote"):
        quotes = [q.strip() for q in str(data["quote"]).split("|||") if q.strip()]
    pids = [data["passage_id"]] if data.get("passage_id") else []
    reason = NEIReason(data["reason"]) if (label == VerdictLabel.NEI and data.get("reason")) \
        else (NEIReason.NO_EVIDENCE if label == VerdictLabel.NEI else None)
    return Verdict(label=label, reason=reason, quotes=quotes, passage_ids=pids,
                   confidence=data.get("confidence", "medium"), model=f"live:{_model_name(llm)}")


def _model_name(llm: LLM) -> str:
    return getattr(llm, "model", "unknown")


def verify_live(claim: Claim, retriever: Retriever, cfg: Settings, llm: LLM) -> Verdict:
    """Fresh retrieval → judge → quote guard (1 retry) → bounded query reformulation."""
    query = claim.text
    iterations = 0
    for attempt in range(cfg.budgets.retrieval_retries_per_claim + 1):
        passages = {p.passage_id: p for p in retriever.search(query, k=cfg.top_k_passages)}
        if not passages:
            iterations += 1
            query = _reformulate(claim, llm)
            continue
        verdict = _judge(claim, passages, llm, cfg)
        iterations += 1

        # quote guard: one retry with explicit feedback, then degrade honestly
        violations = quote_substring_check(verdict, passages)
        if violations:
            block = "\n\n".join(f"[{pid}] {p.text}" for pid, p in passages.items())
            raw = llm.complete(
                SYSTEM,
                f"Claim: {claim.text}\n\nEvidence passages:\n{block}\n\n"
                f"Your previous verdict failed validation: {violations}. "
                f"Quotes MUST be exact substrings of a cited passage. Try again.",
                max_tokens=1000)
            try:
                data = extract_json(raw)
                verdict = _judge_from(data, llm)
                iterations += 1
            except Exception:
                pass
            if quote_substring_check(verdict, {p.passage_id: p for p in passages.values()}):
                verdict = Verdict(label=VerdictLabel.NEI, reason=NEIReason.TOOL_ERROR,
                                  quotes=[], passage_ids=[],
                                  confidence="low", model=f"live:{_model_name(llm)}")

        if verdict.label != VerdictLabel.NEI or verdict.reason != NEIReason.NO_EVIDENCE \
                or attempt == cfg.budgets.retrieval_retries_per_claim:
            verdict.iterations = iterations
            return verdict
        query = _reformulate(claim, llm)  # NEI(no_evidence) and budget remains → new angle

    v = Verdict(label=VerdictLabel.NEI, reason=NEIReason.BUDGET_EXHAUSTED,
                model=f"live:{_model_name(llm)}")
    v.iterations = iterations
    return v


def _judge_from(data: dict, llm: LLM) -> Verdict:
    label = VerdictLabel(data["label"])
    quotes = [q.strip() for q in str(data.get("quote") or "").split("|||") if q.strip()]
    pids = [data["passage_id"]] if data.get("passage_id") else []
    reason = NEIReason(data["reason"]) if (label == VerdictLabel.NEI and data.get("reason")) \
        else (NEIReason.NO_EVIDENCE if label == VerdictLabel.NEI else None)
    return Verdict(label=label, reason=reason, quotes=quotes, passage_ids=pids,
                   confidence=data.get("confidence", "medium"), model=f"live:{_model_name(llm)}")


def _reformulate(claim: Claim, llm: LLM) -> str:
    try:
        data = extract_json(llm.complete(REFORM_SYSTEM, f"Claim: {claim.text}", max_tokens=200))
        return str(data.get("query") or claim.text)
    except Exception:
        return claim.text
