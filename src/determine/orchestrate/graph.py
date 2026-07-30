"""LangGraph orchestration: plan → gate → execute → answer → decompose → verify ∥ compute
→ fuse → score → (kg_write no-op) → report.

Every node is `RunState -> RunState`. In dry-run mode nodes emit deterministic stub output so
the whole loop runs end-to-end with zero LLM calls — Phase 0's "runnable skeleton".

Structural independence (plan v2 §2): `verify_blind` receives ONLY the claim and a fresh
retriever handle — the wiring below never passes it the answer, citations, or notebook.
"""

from __future__ import annotations

from pathlib import Path

from determine.config import Settings
from determine.retrieve.bm25 import Retriever
from determine.schema import (
    Answer,
    Claim,
    ClaimType,
    EntityCard,
    NEIReason,
    PlanStep,
    RetrievalRecord,
    RunState,
    StepType,
    Verdict,
    VerdictLabel,
)
from determine.verify.guards import quote_substring_check

# ── nodes ───────────────────────────────────────────────────────────────────

def _llm(cfg: Settings, role: str):
    """Lazy client factory — vendor SDKs only load in live mode."""
    from determine.llm.client import load_dotenv, make_client
    load_dotenv()
    r = getattr(cfg, role)
    return make_client(r.family, r.name)


def plan_node(state: RunState, cfg: Settings) -> RunState:
    """Stage-A planner: question → typed steps (GROUND/GATHER/COMPUTE/COMPARE/CONCLUDE)."""
    if cfg.dry_run:
        state.plan = [
            PlanStep(id="S1", type=StepType.GROUND, goal=f"Ground entities in: {state.question}"),
            PlanStep(id="S2", type=StepType.GATHER, goal="Gather evidence",
                     retrieval_seeds=[state.question], inputs=["S1"]),
            PlanStep(id="S3", type=StepType.CONCLUDE, goal="Cited answer", inputs=["S1", "S2"]),
        ]
        state.entity_cards = [EntityCard(slug="stub-entity", name="Stub Entity")]
    else:
        from determine.orchestrate.planner import plan_live
        state = plan_live(state, cfg, _llm(cfg, "planner"))
    return state


def plan_gate(state: RunState, cfg: Settings) -> RunState:
    """Rule checks first (pure code), then ≤1 LLM review revision."""
    ids = {s.id for s in state.plan}
    problems = []
    if not 3 <= len(state.plan) <= 6 and not cfg.dry_run:
        problems.append("plan length outside 3-6")
    for s in state.plan:
        if any(i not in ids for i in s.inputs):
            problems.append(f"{s.id}: unknown input")
        if s.type == StepType.GATHER and not s.retrieval_seeds:
            problems.append(f"{s.id}: GATHER without seeds")
    state.plan_review_status = "accepted" if not problems else f"rejected: {problems}"
    if problems:
        raise AssertionError(f"plan gate failed: {problems}")
    return state


def execute_steps(state: RunState, cfg: Settings, retriever: Retriever) -> RunState:
    for step in state.plan:
        if step.type == StepType.GATHER:
            passages = retriever.search(step.retrieval_seeds[0], k=cfg.top_k_passages)
            state.retrieval_log.append(RetrievalRecord(
                for_id=step.id, queries=step.retrieval_seeds,
                passage_ids=[p.passage_id for p in passages]))
            state.notebook.append(f"{step.id}: {len(passages)} passages")
        step.status = "done"
        step.committed_result = step.committed_result or f"[stub] {step.goal}"
    return state


def answer_node(state: RunState, cfg: Settings, retriever: Retriever) -> RunState:
    """Grounded answerer under the cite-or-abstain contract."""
    if cfg.dry_run:
        passages = retriever.search(state.question, k=2)
        cites = [p.passage_id for p in passages]
        state.answer = Answer(
            text="Stub sentence one. Stub sentence two with a value of 80.4 GeV.",
            sentence_citations={0: cites[:1], 1: cites[:1]},
        )
    else:
        from determine.answer.answerer import answer_live
        state = answer_live(state, cfg, retriever, _llm(cfg, "answerer"))
    return state


def decompose_node(state: RunState, cfg: Settings) -> RunState:
    """Stage-B: answer → typed atomic claims."""
    if cfg.dry_run:
        state.claims = [
            Claim(text="Stub sentence one.", type=ClaimType.REPORT, source_sentences=[0]),
            Claim(text="The stub quantity equals 80.4 GeV.", type=ClaimType.NUMERIC,
                  source_sentences=[1]),
        ]
    else:
        from determine.decompose.decomposer import decompose_live
        state = decompose_live(state, cfg, _llm(cfg, "decomposer"))
    return state


def verify_blind(claim: Claim, retriever: Retriever, cfg: Settings,
                 retrieval_log: list | None = None) -> Verdict:
    """Independent verifier: sees ONLY the bare claim + its own fresh retrieval.

    Model-independence: in live mode this calls cfg.verifier (different family from the
    answerer — asserted at startup). Quote guard is enforced here, with bounded retries.
    """
    if cfg.dry_run:
        passages = {p.passage_id: p for p in retriever.search(claim.text, k=cfg.top_k_passages)}
        if retrieval_log is not None:
            retrieval_log.append(RetrievalRecord(
                for_id=claim.claim_id, queries=[claim.text],
                passage_ids=list(passages.keys())))
        if passages:
            pid, p = next(iter(passages.items()))
            quote = p.text[:40]
            v = Verdict(label=VerdictLabel.SUPPORTED, quotes=[quote], passage_ids=[pid],
                        model="dry-run")
            assert not quote_substring_check(v, passages)
            return v
        return Verdict(label=VerdictLabel.NEI, reason=NEIReason.NO_EVIDENCE, model="dry-run")
    from determine.verify.verifier import verify_live
    return verify_live(claim, retriever, cfg, _llm(cfg, "verifier"), retrieval_log)


def numeric_check(claim: Claim, cfg: Settings) -> Claim:
    """Numeric checker (in MVP): four check types; declines anything else."""
    from determine.compute.numeric_checker import check_claim
    return check_claim(claim, cfg)


def fuse_and_score(state: RunState) -> RunState:
    state.assert_verdict_totality()
    state.compute_score()
    state.status = "complete"
    return state


def kg_write(state: RunState, cfg: Settings) -> RunState:
    """No-op in MVP (kg.enabled=False). Phase 2: AssertionMapper + KGStore.commit."""
    state.kg_write_status = "disabled" if not cfg.kg.enabled else "pending"
    return state


def persist(state: RunState, cfg: Settings) -> Path:
    out = Path(cfg.runs_dir) / f"{state.run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(state.model_dump_json(indent=2))
    return out


# ── pipeline ────────────────────────────────────────────────────────────────

def run_pipeline(question: str, cfg: Settings, retriever: Retriever) -> RunState:
    """Sequential reference pipeline (identical node order to the LangGraph build)."""
    state = RunState(question=question, config_hash=cfg.config_hash(),
                     corpus_version=cfg.corpus_version,
                     model_per_role={"answerer": cfg.answerer.name, "planner": cfg.planner.name,
                                     "decomposer": cfg.decomposer.name,
                                     "verifier": cfg.verifier.name})
    try:
        state = plan_node(state, cfg)
        state = plan_gate(state, cfg)
        state = execute_steps(state, cfg, retriever)
        state = answer_node(state, cfg, retriever)
        state = decompose_node(state, cfg)
        for claim in state.claims:
            claim.verdict = verify_blind(claim, retriever, cfg,
                                         state.retrieval_log)   # blind: claim only
            if claim.type in (ClaimType.NUMERIC, ClaimType.COMPARATIVE):
                numeric_check(claim, cfg)
        state = fuse_and_score(state)
        state = kg_write(state, cfg)
    except Exception as e:  # failure is a state, never silence (MVP §5)
        state.status = "failed"
        state.error = f"{type(e).__name__}: {e}"
    persist(state, cfg)
    return state


def build_langgraph(cfg: Settings, retriever: Retriever):
    """Optional LangGraph wrapper around the same nodes (used when langgraph is installed)."""
    from langgraph.graph import END, StateGraph

    g = StateGraph(dict)

    def wrap(fn, *extra):
        def node(d: dict) -> dict:
            state = RunState.model_validate(d)
            return fn(state, *extra).model_dump()
        return node

    g.add_node("plan", wrap(plan_node, cfg))
    g.add_node("gate", wrap(plan_gate, cfg))
    g.add_node("execute", wrap(execute_steps, cfg, retriever))
    g.add_node("answer", wrap(answer_node, cfg, retriever))
    g.add_node("decompose", wrap(decompose_node, cfg))

    def verify_all(d: dict) -> dict:
        state = RunState.model_validate(d)
        for claim in state.claims:
            claim.verdict = verify_blind(claim, retriever, cfg, state.retrieval_log)
            if claim.type in (ClaimType.NUMERIC, ClaimType.COMPARATIVE):
                numeric_check(claim, cfg)
        return state.model_dump()

    g.add_node("verify", verify_all)
    g.add_node("fuse", lambda d: fuse_and_score(RunState.model_validate(d)).model_dump())
    g.add_node("kg_write", wrap(kg_write, cfg))
    g.set_entry_point("plan")
    for a, b in [("plan", "gate"), ("gate", "execute"), ("execute", "answer"),
                 ("answer", "decompose"), ("decompose", "verify"), ("verify", "fuse"),
                 ("fuse", "kg_write")]:
        g.add_edge(a, b)
    g.add_edge("kg_write", END)
    return g.compile()
