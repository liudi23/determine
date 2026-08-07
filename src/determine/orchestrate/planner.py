"""Live Stage-A planner: question → typed research plan + entity cards (JSON contract)."""

from __future__ import annotations

from determine.config import Settings
from determine.llm.client import LLM, extract_json
from determine.schema import EntityCard, NeedsComputation, PlanStep, RunState, StepType

SYSTEM = """You are the research planner of Determine, a scientific claim-verification agent
for high-energy physics (hep-ph). Decompose the user's question into an ordered plan of
3-6 typed steps. Step types (closed set):
- GROUND: pin down entities, conventions, parameter definitions BEFORE retrieval
- GATHER: one focused evidence sub-question, with 2-4 retrieval query seeds
- COMPUTE: a derivable number (unit conversion, ratio, tension-in-sigma); set
  needs_computation.flag=true with reasoning
- COMPARE: synthesis across earlier steps (overlap, agreement, coverage)
- CONCLUDE: assemble the cited answer; must depend on all other steps

Rules: first step is GROUND; last is CONCLUDE; every GATHER has retrieval_seeds;
quantitative deliverables are fed by a COMPUTE step; keep goals concrete and checkable.

BE COMPACT — this is machine-parsed, not prose: entity cards limited to 3 aliases,
3 canonical_params, one-line convention; step goals one sentence; no markdown fences,
no commentary. The COMPLETE JSON must fit in the response — never let it truncate.

Return ONLY JSON:
{"entity_cards": [{"slug": str, "name": str, "aliases": [str], "convention": str,
                   "canonical_params": {str: str}}],
 "steps": [{"id": "S1", "type": str, "goal": str, "inputs": [str],
            "retrieval_seeds": [str],
            "needs_computation": {"flag": bool, "reasoning": str},
            "deliverable": str, "rubric": [str]}]}"""


def plan_live(state: RunState, cfg: Settings, llm: LLM) -> RunState:
    raw = llm.complete(SYSTEM, f"Question: {state.question}", max_tokens=8000)
    data = extract_json(raw)
    if isinstance(data, dict) and "steps" not in data and "plan" in data:
        data["steps"] = data["plan"]  # tolerate the common alias
    if not isinstance(data, dict) or "steps" not in data:
        # one bounded retry with explicit feedback (truncated/invalid first response)
        raw = llm.complete(
            SYSTEM,
            f"Question: {state.question}\n\nYour previous response was truncated or "
            f"missing the required 'steps' key. Respond again with the COMPLETE compact "
            f"JSON object — brief entity cards, all steps included.",
            max_tokens=8000)
        data = extract_json(raw)
    if not isinstance(data, dict) or "steps" not in data:
        raise ValueError("planner response missing 'steps' after retry — see llm cache")
    state.entity_cards = [EntityCard(**c) for c in data.get("entity_cards", [])]
    steps = []
    for s in data["steps"]:
        nc = s.get("needs_computation") or {"flag": False, "reasoning": ""}
        steps.append(PlanStep(
            id=s["id"], type=StepType(s["type"]), goal=s["goal"],
            inputs=s.get("inputs", []), retrieval_seeds=s.get("retrieval_seeds", []),
            needs_computation=NeedsComputation(**nc),
            deliverable=s.get("deliverable", ""), rubric=s.get("rubric", []),
        ))
    state.plan = steps
    return state
