"""Determine run-state schema — the single source of truth for every run.

This module encodes the invariants fixed in the MVP proposal:
- every claim terminates in exactly one of SUPPORTED / REFUTED / NEI(reason)  (verdict totality)
- all IDs are stable and never reused (KG-readiness, plan v2 §11)
- the persisted run state is the audit trail, the debug tool, and the demo backend
"""

from __future__ import annotations

import enum
import hashlib
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def span_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Verdicts ────────────────────────────────────────────────────────────────

class VerdictLabel(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    NEI = "NOT-ENOUGH-EVIDENCE"


class NEIReason(str, enum.Enum):
    NO_EVIDENCE = "no_evidence"
    CONFLICT = "conflict"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TOOL_ERROR = "tool_error"


class Verdict(BaseModel):
    verdict_id: str = Field(default_factory=lambda: new_id("v"))
    label: VerdictLabel
    reason: NEIReason | None = None  # required iff label == NEI (validated below)
    quotes: list[str] = []           # verbatim substrings of cited passages (checked)
    passage_ids: list[str] = []
    confidence: str = "medium"       # low | medium | high — logged, not scored
    model: str = ""
    iterations: int = 0
    verified_at: str = Field(default_factory=utcnow)

    def model_post_init(self, __context) -> None:
        if self.label == VerdictLabel.NEI and self.reason is None:
            raise ValueError("NEI verdict requires a reason code")
        if self.label != VerdictLabel.NEI and self.reason is not None:
            raise ValueError("reason code only valid for NEI")


# ── Plan (Stage A decomposition) ────────────────────────────────────────────

class StepType(str, enum.Enum):
    GROUND = "GROUND"
    GATHER = "GATHER"
    COMPUTE = "COMPUTE"
    COMPARE = "COMPARE"
    CONCLUDE = "CONCLUDE"


class NeedsComputation(BaseModel):
    flag: bool
    reasoning: str = ""


class PlanStep(BaseModel):
    id: str
    type: StepType
    goal: str
    inputs: list[str] = []
    retrieval_seeds: list[str] = []
    needs_computation: NeedsComputation = NeedsComputation(flag=False)
    deliverable: str = ""
    rubric: list[str] = []
    status: str = "pending"          # pending | done | failed
    committed_result: str = ""


class EntityCard(BaseModel):
    """KG-ready structured entity from the GROUND step (plan v2 §11)."""
    slug: str
    name: str
    aliases: list[str] = []
    convention: str = ""
    canonical_params: dict[str, str] = {}


# ── Claims (Stage B decomposition) ──────────────────────────────────────────

class ClaimType(str, enum.Enum):
    REPORT = "report"
    NUMERIC = "numeric"
    COMPARATIVE = "comparative"
    HEDGED = "hedged"


class Quantity(BaseModel):
    """Unit-normalized measurement payload (pint canonical form)."""
    quantity: str                    # e.g. "m_W"
    value: float
    unit: str                        # canonical, e.g. "GeV"
    uncertainty: float | None = None
    relation: str = "="              # = | < | >


class Computation(BaseModel):
    computation_id: str = Field(default_factory=lambda: new_id("c"))
    script: str = ""
    output: str = ""
    status: str = "pending"          # pending | ok | failed | not_checkable
    tolerance_rule: str = "relative_5pct"
    iterations: int = 0


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: new_id("cl"))
    text: str
    type: ClaimType
    source_sentences: list[int] = []
    quantity: Quantity | None = None
    verdict: Verdict | None = None   # None only mid-run; must be set at terminal state
    computation: Computation | None = None


# ── Retrieval / answer ──────────────────────────────────────────────────────

class Passage(BaseModel):
    passage_id: str                  # f"{paper_id}#{span_hash}"
    paper_id: str
    text: str
    score: float = 0.0


class RetrievalRecord(BaseModel):
    for_id: str                      # step id or claim id
    queries: list[str]
    passage_ids: list[str]


class Answer(BaseModel):
    text: str = ""
    sentence_citations: dict[int, list[str]] = {}   # sentence index -> passage_ids


# ── Score / run ─────────────────────────────────────────────────────────────

class Score(BaseModel):
    supported: int = 0
    refuted: int = 0
    nei: int = 0
    headline: float = 0.0            # strict: supported / total claims

    @property
    def total(self) -> int:
        return self.supported + self.refuted + self.nei


class RunState(BaseModel):
    """The LangGraph state object AND the persisted audit record."""
    run_id: str = Field(default_factory=lambda: new_id("r"))
    question: str = ""
    config_hash: str = ""
    corpus_version: str = ""
    model_per_role: dict[str, str] = {}
    started_at: str = Field(default_factory=utcnow)
    plan: list[PlanStep] = []
    plan_review_status: str = "pending"
    entity_cards: list[EntityCard] = []
    notebook: list[str] = []
    retrieval_log: list[RetrievalRecord] = []
    answer: Answer = Answer()
    claims: list[Claim] = []
    score: Score = Score()
    status: str = "running"          # running | complete | partial | failed
    error: str | None = None
    # KG-readiness (no-op in MVP; plan v2 §11)
    kg_write_status: str = "disabled"

    # ── invariants ──────────────────────────────────────────────────────
    def assert_verdict_totality(self) -> None:
        """Every claim must carry exactly one terminal verdict. (MVP §5)"""
        missing = [c.claim_id for c in self.claims if c.verdict is None]
        if missing:
            raise AssertionError(f"claims without terminal verdict: {missing}")

    def compute_score(self) -> Score:
        s = Score()
        for c in self.claims:
            assert c.verdict is not None
            if c.verdict.label == VerdictLabel.SUPPORTED:
                s.supported += 1
            elif c.verdict.label == VerdictLabel.REFUTED:
                s.refuted += 1
            else:
                s.nei += 1
        s.headline = round(s.supported / s.total, 4) if s.total else 0.0
        self.score = s
        return s
