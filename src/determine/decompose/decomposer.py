"""Live Stage-B decomposer — answer → typed, decontextualized atomic claims."""

from __future__ import annotations

from determine.config import Settings
from determine.llm.client import LLM, extract_json
from determine.schema import Claim, ClaimType, Quantity, RunState

SYSTEM = """You are the claim decomposer of Determine, a scientific claim-verification agent.
Split the answer into ATOMIC claims: single-predicate, decontextualized statements
(entities resolved, no pronouns, no cross-sentence references) that a physicist could
check against the literature in isolation.

Types:
- "report": what a paper/experiment reports ("PROSPECT excludes X at 95% CL")
- "numeric": carries a specific quantity; ALSO fill the structured "quantity" object
- "comparative": relation between two results ("A is in tension with B at 2 sigma")
- "hedged": the hedge is part of the claim ("evidence suggests X") — keep the hedge

Rules: skip pure-abstention sentences ("the literature does not establish...");
each claim records the 0-based indices of the answer sentences it came from;
for numeric claims normalize the unit to a canonical symbol (GeV, MeV, eV^2, fb, ...).

Return ONLY JSON:
{"claims": [{"text": str, "type": str, "source_sentences": [int],
             "quantity": {"quantity": str, "value": float, "unit": str,
                          "uncertainty": float | null, "relation": "="} | null}]}"""


def decompose_live(state: RunState, cfg: Settings, llm: LLM) -> RunState:
    if not state.answer.text or state.answer.text.startswith("NOT ENOUGH EVIDENCE"):
        state.claims = []
        return state
    raw = llm.complete(SYSTEM, f"Answer to decompose:\n{state.answer.text}", max_tokens=2500)
    data = extract_json(raw)
    claims = []
    for c in data["claims"]:
        q = c.get("quantity")
        claims.append(Claim(
            text=c["text"], type=ClaimType(c["type"]),
            source_sentences=c.get("source_sentences", []),
            quantity=Quantity(**q) if q else None,
        ))
    state.claims = claims
    return state
