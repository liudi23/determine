# Determine — Project Plan v2: verification pipeline + persistent scientific knowledge graph

**Author:** prepared for Di Liu · **Date:** 2026-07-27 · **Status:** revision for sign-off
**Supersedes:** `determine-plan.md` (v1) and extends `determine-mvp-proposal.md`; all decisions
fixed there (verdict contract, model independence, budgets, numeric checker in MVP, hep-ph,
~10 demo questions) remain in force unless explicitly amended below.

---

## The two-layer principle (read this first)

- **LangGraph controls *how* Determine reasons and executes workflows** — planning, branching,
  retries, independent retrieval, computation, and (new) knowledge-graph updates. It is
  stateful *per run* and its state dies with the run (persisted as an audit record).
- **The knowledge graph records *what* Determine has extracted, computed, and verified** from
  scientific evidence. It is persistent *across runs*, provenance-aware, and append-only.

Nothing in the verification-first architecture is replaced or weakened. The KG is a
**derived, downstream consumer** of the verification pipeline: verdicts are produced exactly
as before, then *additionally* written into a persistent graph where they can be queried and
reused. The long-term goal is not a general scientific knowledge graph platform, but an
auditable, provenance-aware, continuously extensible **graph of claims and evidence produced
by Determine's own verification pipeline**.

---

## 1 · Updated system architecture

```
Question
  → Research planning            (planner: GROUND/GATHER/COMPUTE/COMPARE/CONCLUDE, plan gate)
  → [Phase 3+] KG lookup         (prior verified claims as *context*, never as ground truth)
  → Scientific retrieval         (BM25 → hybrid later; arXiv hep-ph abstracts)
  → Evidence-grounded answer     (cite-or-abstain RAG)
  → Atomic claim extraction      (typed claims: report / numeric / comparative / hedged)
  → [Verification ∥ Computation] (blind verifier, fresh retrieval; numeric checker)
  → Verdicts                     (SUPPORTED / REFUTED / NEI(reason); totality invariant)
  → KG construction / update     (assertion writer: papers, claims, entities, measurements,
                                  methods, evidence, computations, verdicts + provenance)
  → Auditable report             (score triple + clickable trail; now also graph-linked)
```

Two architectural additions, and only two:

1. **`kg_write`** — a terminal pipeline stage that translates a *completed, invariant-checked*
   run state into graph assertions. It sits after verdicts, off the critical path: a
   `kg_write` failure degrades the run to `partial`, it never blocks the report.
2. **`kg_lookup`** (Phase 3, feature-flagged off before that) — an early stage that queries
   the accumulated graph for entities in the question and returns prior claims/verdicts as
   dated, provenance-stamped *context cards* for the planner and answerer — **never** for
   the verifier.

Everything between planning and verdicts is unchanged from the MVP proposal.

## 2 · LangGraph state and node design

**State.** The persisted run-state schema from the MVP proposal §5 *is* the LangGraph state
object (single source of truth — no parallel bookkeeping). v2 adds four fields:

```
entity_cards:   [{slug, name, aliases[], convention, canonical_params}]   # from GROUND
kg_context:     [{claim_id, text, verdict, verified_at, run_id, staleness}]  # Phase 3 input
kg_assertions:  [Assertion]        # staged during kg_write, then committed
kg_write_status: pending | committed | failed(reason)
```

**Nodes** (LangGraph graph; ∥ = fan-out):

```
plan → plan_gate ──(≤1 revision)──→ kg_lookup* → step_executor loop
      step_executor: GATHER → retrieve → evidence_table
                     COMPUTE → numeric tool (reflect ≤1) → committed result
answer → decompose → ∥ per-claim: [fresh_retrieve → verify_blind] ∥ [numeric_check if typed]
      → fuse_verdicts → score → kg_write* → report          (* = new node)
```

**Branching and retries** (unchanged budgets from MVP §5, now edges in the graph): retrieval
reformulation ≤2 per claim on NEI(no_evidence); numeric-checker reflect ≤1; plan revision ≤1;
every loop edge carries an explicit counter in state so budget exhaustion is a state
transition to `NEI(budget_exhausted)`, not an exception.

**Independence enforced structurally:** the `verify_blind` node's input channel contains only
`{claim.text, claim.quantity?}` plus its own retriever handle. Neither the answer, nor the
answerer's citations, nor `kg_context` is reachable from that node — the graph wiring itself
guarantees verifier blindness, not just a prompt instruction.

## 3 · Knowledge-graph schema / ontology

**Node types (closed set of 9 — frozen for Phases 2–3):**

| Node | Key properties | Identity key |
|---|---|---|
| `Paper` | title, year, venue, abstract hash | arXiv ID (DOI later) |
| `Evidence` (passage) | text span, char offsets, corpus_version | (paper_id, span hash) |
| `Claim` | text, type (report/numeric/comparative/hedged), origin (answer/injected) | claim_id (run-scoped UUID) |
| `Entity` | canonical name, aliases, convention notes | slug from entity card |
| `Measurement` | quantity, value, unit, uncertainty, relation (=,<,>) | (entity, quantity, value, unit, paper) |
| `Method` | name, category (experiment/lattice/global-fit/…) | slug |
| `Computation` | script hash, inputs, output, tolerance rule, status | computation_id |
| `Verdict` | label, reason_code, confidence, verifier model | verdict_id |
| `Run` | question, config_hash, corpus_version, timestamps, score triple | run_id |

**Edge types** (directed; the user-specified core set plus four structural ones):

```
Paper      —reports→        Claim          Claim  —concerns→       Entity
Claim      —supported_by→   Evidence       Claim  —contradicted_by→ Evidence
Claim      —has_verdict→    Verdict        Claim  —derived_by→     Computation
Entity     —has_measurement→ Measurement   Measurement —obtained_using→ Method
Measurement —reported_by→   Paper
Claim      —conflicts_with→ Claim          # structural: preserved disagreement (§8)
Entity     —same_as→        Entity         # structural: soft entity resolution (§6)
Run        —produced→       {Claim, Verdict, Computation}   # structural: provenance root
Verdict    —based_on→       Evidence       # structural: which passages the verifier quoted
```

**Verdicts become graph citizens, not only terminal outputs** — the answer to the design
question posed: `Claim —has_verdict→ Verdict` is an edge to a *node* (not a property),
because a claim can accumulate **multiple verdicts over time** (re-verification in different
runs, by different verifier models, against different corpus versions). The latest verdict is
a query (`ORDER BY verified_at DESC LIMIT 1`), not an overwrite. Verdict history is exactly
how the graph represents "science may change" without ever deleting anything.

## 4 · Provenance model

Every edge in the graph is a **reified assertion** — the atomic unit of the store:

```json
{
  "assertion_id": "a_...", "subject": "claim:c42", "predicate": "supported_by",
  "object": "evidence:2203.01234#s3",
  "provenance": {
    "run_id": "r_...",                      // → full audit trail via run state
    "derived_from": ["claim:c42", "verdict:v17"],  // pipeline objects that justify it
    "asserted_by": {"role": "verifier", "model": "..."},
    "corpus_version": "hepph-2026-07-01",
    "timestamp": "..."
  }
}
```

Three consequences, all load-bearing:

- **Complete traceability:** any graph fact walks back to run → plan step → passage →
  claim → computation → verdict, because `run_id` links into the already-persisted run
  state. The KG never contains information that is absent from some run's audit record.
- **The KG is a *derived view*, rebuildable at any time:** `kg_build(run_states) → graph`
  is deterministic. Run states remain the single source of truth; if the schema evolves,
  drop the graph and rebuild — no migration, no divergence risk.
- **Append-only:** assertions are never edited or deleted; corrections are new assertions
  (e.g. a new Verdict node). "The graph on date D" is reconstructible by filtering on
  timestamp — cheap temporal versioning long before Phase 4 builds anything fancier.

## 5 · Entity and relation extraction

**Principle: extraction is a byproduct of the existing pipeline, not a new NLP stage.** This
is the main thing keeping the KG affordable in the MVP timeframe:

- **Entities** come from the planner's GROUND step, which already produces entity cards
  `{name, aliases, convention, canonical_params}` — the card *is* the Entity node payload.
- **Claims, typed relations, and measurements** come from the claim decomposer, which
  already types claims and extracts structured quantities for numeric claims — a numeric
  claim's `{quantity, value, unit, uncertainty}` *is* the Measurement node.
- **Evidence links** come from the verifier, whose quote-substring-checked citations *are*
  the `supported_by`/`contradicted_by`/`based_on` edges.
- **Methods** are the one genuinely new extraction: a lightweight tag on GATHER evidence
  rows ("reactor experiment", "lattice QCD", "global EW fit"), from a small closed
  vocabulary per domain, LLM-tagged with a rule fallback of `method:unknown`. Kept
  deliberately coarse in Phase 2.

New component: a pure-code **`AssertionMapper`** (`run_state → [Assertion]`) — no LLM calls,
fully unit-testable, deterministic. This is the interface between the pipeline and the graph.

## 6 · Entity resolution and deduplication

Wrong merges are the classic way knowledge graphs rot, so resolution is **conservative and
non-destructive**:

- **Papers:** arXiv ID — exact, solved.
- **Entities (Phase 2):** deterministic only — slug match after normalization, plus alias
  lists from entity cards (`"RAA" ≡ "reactor antineutrino anomaly"`). A match creates a
  `same_as` edge; nodes are **never destructively merged**. Queries traverse `same_as`
  closures, so an incorrect link is repaired by retracting one edge, not by un-merging data.
- **Measurements:** identity key (entity, quantity, value, unit, paper) — two papers
  reporting the same value remain two Measurement nodes with different `reported_by`
  provenance, which is correct: replication is information.
- **Claims:** near-duplicate claims across runs are linked `same_as` by normalized-text
  match (Phase 2) — semantic/embedding similarity is **Phase 4**, as is cross-domain
  ontology alignment and ML-based ER generally.

## 7 · Integration: claim extraction ⇄ verification ⇄ computation ⇄ KG construction

The integration contract in one sentence: **only invariant-checked, terminal run states are
graphed.** `kg_write` runs after `score`, and refuses states that fail the verdict-totality
invariant. Flow per run:

1. `fuse_verdicts` completes → every claim has exactly one terminal verdict this run.
2. `AssertionMapper` walks the run state: papers/evidence from the retrieval log; entities
   from entity cards; claims + measurements from the decomposer output; computations from
   the numeric checker log; verdicts + evidence edges from the verifier output; everything
   rooted at the Run node.
3. Assertions staged in `kg_assertions` → committed transactionally to the store →
   `kg_write_status: committed`. On failure: `failed(reason)`, run marked `partial`, report
   still ships, and a rebuild pass can re-graph the run later from its persisted state.

Computation results integrate as first-class provenance: a numeric claim verified by both
retrieval and computation carries `supported_by → Evidence` *and* `derived_by →
Computation`; when the two disagree, the claim's verdict is `NEI(conflict)` (per MVP §6) and
**both** edges are written — the graph records the disagreement instead of arbitrating it.

## 8 · Conflicting evidence and scientific uncertainty

The graph's job is to **represent disagreement, not resolve it**. Concretely:

- Competing claims coexist as separate Claim nodes joined by `conflicts_with` (created when
  the verifier finds contradicting evidence for one claim that supports another, or when two
  runs yield opposing verdicts on `same_as` claims). Nothing is collapsed into "the fact."
- Multiple measurements of the same quantity all persist (§6) — the CDF vs ATLAS W-mass
  situation is *two* Measurement nodes on one Entity, each with its own uncertainty, method,
  and paper, plus any tension computation as a Computation node linking them.
- NEI is a real outcome in the graph, with its reason code (`no_evidence` vs `conflict` vs
  `budget_exhausted` mean scientifically different things and remain distinguishable).
- Uncertainty lives in three places, deliberately separate: measurement uncertainty
  (Measurement properties), verifier confidence (Verdict property), and epistemic conflict
  (`conflicts_with` topology + NEI(conflict) verdicts). They are never summed into one
  "belief score" — that would be modeling, and Determine reports, it does not adjudicate.
- Hedged claims stay hedged: the claim text preserved in the node is the hedged form, so the
  graph asserts "evidence suggests X," never silently "X."

## 9 · Persistence and graph-database options

| Option | Verdict for Determine |
|---|---|
| **SQLite (2 tables: nodes, assertions) + NetworkX in-memory view** | **Phase 2 choice.** Zero ops, transactional, trivially versioned/backed up, embarrassingly sufficient for the scale (10 questions ≈ low hundreds of nodes). Export to GraphML/JSON for visualization. |
| Kùzu (embedded, Cypher) | Attractive Phase 3 upgrade if multi-hop queries in `kg_lookup` get awkward in SQL/NetworkX; embedded → still zero ops. |
| Neo4j | Phase 4, only if scale or a served multi-user graph demands it; operational cost not justified before. |
| RDF triple store / OWL | Rejected for now: reification overhead and ontology ceremony without a consumer; the assertion model above captures the useful part (provenance-per-edge) in plain rows. |

The pipeline sees only a thin **`KGStore` interface** (`commit(assertions)`,
`find_entity(slug|alias)`, `claims_for(entity)`, `verdict_history(claim)`,
`neighbors(node, edge_types, depth)`), so the backend is swappable without touching any node.

## 10 · Retrieval from literature *and* the accumulated graph (Phase 3)

`kg_lookup` runs after planning, and its output is **context, never ground truth**:

- Entities in the question (via GROUND cards) → `same_as` closure → prior claims with their
  **full verdict history**, each rendered as a context card:
  `"[KG] verified SUPPORTED on 2026-08-14 (run r_…, verifier model M, corpus v…): <claim>"`.
- Uses: seed GROUND (known aliases/conventions), sharpen GATHER retrieval seeds, and let the
  answerer cite prior verified claims *as prior Determine results, dated and attributed* —
  visibly distinct from fresh literature citations in the report.
- **Independence preserved — three hard rules:**
  1. The verifier never sees `kg_context` (enforced by graph wiring, §2). Every claim in
     every answer is verified fresh, every run, full stop.
  2. **Staleness policy:** KG claims older than a configurable window (default 90 days), or
     with corpus_version older than current, are marked `stale` on the context card and
     trigger a re-verification GATHER step — a new Verdict node results either way.
  3. A KG claim whose fresh re-verification disagrees with its stored verdict gets a
     `conflicts_with`-style verdict-history entry — the disagreement is surfaced in the
     report ("previously SUPPORTED, now NEI(conflict)"), which is a *feature*: Determine
     noticing that the literature moved.

Literature retrieval is unchanged and always available; the KG can only add context, never
substitute for fresh evidence.

## 11 · Changes required to the MVP (kept deliberately tiny)

The MVP (= Phase 1) **ships without a graph.** It changes only enough to be KG-ready:

1. **Stable IDs everywhere** — claim_id, passage_id = (paper, span hash), entity slugs,
   computation_id already implied by the run-state schema; now mandatory and never reused.
2. **Entity cards persisted** in run state (the GROUND step already produces them; they must
   be stored structured, not prose).
3. **Structured Measurement extraction** for numeric claims (already in the decomposer
   design — unchanged, just flagged as a KG identity key, so units must be normalized:
   `pint` canonical form).
4. **Config flag `kg.enabled = false`** and the `KGStore` interface defined (one file,
   no implementation beyond a no-op).

Cost of KG-readiness: roughly a day. Everything else about the MVP proposal — scope, demo
set, metrics, budgets, definition of done — is unchanged.

## 12 · Testing and evaluation strategy for KG correctness

- **Provenance completeness (invariant test):** every assertion resolves to an existing
  run_id and every `derived_from` object exists in that run's state. Zero tolerance.
- **Rebuild determinism (invariant test):** `kg_build(run_states)` twice → isomorphic
  graphs; and rebuild-after-live-writes ≡ live graph. This is the test that keeps "derived
  view" true rather than aspirational.
- **Mapping unit tests:** golden run state → exact expected assertion set (AssertionMapper
  is pure code, so this is cheap and total).
- **Conflict preservation test:** feed two runs with contradictory measurements/claims →
  assert both survive as nodes, `conflicts_with` exists, and no query path returns a merged
  "fact". (The KG analogue of the hallucination-injection test.)
- **ER quality:** small hand-labelled alias set (≈30 pairs from the 10 demo questions) →
  precision/recall of `same_as`; precision is the metric that matters (target ≈1.0 at
  whatever recall follows — wrong merges are the unforgivable error, misses are cheap).
- **Phase 3 A/B:** KG-assisted vs KG-disabled on repeated/related questions — does
  `kg_lookup` improve faithfulness score, reduce tokens/latency, and leave the injection
  detection rate strictly unchanged? (If detection rate moves, independence has leaked —
  hard failure.)
- **Benchmark hygiene extended:** SciFact evaluation always runs `kg.enabled = false`, so
  accumulated knowledge can never leak into the held-out benchmark.

## 13 · Development phases and priorities

- **Phase 1 — MVP as already specified** + the four KG-ready items of §11.
  *Milestone unchanged: 10 questions end-to-end, injection mini-test, definition of done.*
- **Phase 2 — KG persistence (~4–6 days):** AssertionMapper + SQLite KGStore + `kg_write`
  node; batch `kg_build` over Phase-1 run states (the first graph is built retroactively —
  proof of the derived-view property on day one); invariant tests of §12; a simple graph
  visualization (export → single-page viewer) for the demo.
  *Milestone: every run enriches a persistent, provenance-complete graph; demo shows the
  W-mass question as a subgraph.*
- **Phase 3 — KG-assisted answering:** `kg_lookup` node + context cards + staleness policy +
  re-verification flow; A/B evaluation of §12. Runs alongside v1-plan Phase 3 (SciFact, NLI
  baseline) — SciFact work takes priority if time is short, since it is the externally
  legible result.
  *Milestone: a repeated question is answered faster with prior verified context, verified
  fresh, with detection rate unchanged.*
- **Phase 4 — only if evaluation justifies it:** embedding-based ER, richer temporal/
  versioned knowledge (beyond append-only timestamps), contradiction analytics (e.g.
  surfacing the most-contested entities), cross-domain ontology, Kùzu/Neo4j migration,
  multi-domain corpora.

## 14 · Risks introduced by the KG architecture (and containment)

- **Scope creep into a KG platform** — the headline risk. Containment: closed 9-node schema
  frozen through Phase 3; KG strictly a derived view; no feature exists without a consumer
  in the demo or the eval.
- **Stored verdicts ossifying into ground truth** — would silently break the independence
  principle. Containment: verifier blindness to KG enforced in graph wiring; staleness
  policy; A/B guard on detection rate (§12).
- **ER pollution (wrong merges)** — Containment: non-destructive `same_as`, deterministic
  matching only until Phase 4, precision-first ER metric.
- **Double bookkeeping divergence** (graph says X, run states say Y) — Containment: run
  states are the single source of truth; rebuild determinism test; kg_write transactional.
- **Schema churn** — every schema change invalidates accumulated graphs. Containment:
  rebuildability makes this survivable (drop + rebuild), version field on assertions.
- **Cost/latency creep** — Containment: AssertionMapper is LLM-free; the only new LLM call
  in Phases 2–3 is the coarse Method tag; `kg_write` off the critical path.
- **Benchmark leakage via accumulated knowledge** — Containment: `kg.enabled=false` for all
  held-out evaluation, asserted in the eval harness.

## 15 · MVP vs postponed — the explicit line

**In the MVP (Phase 1):** everything in the MVP proposal, plus stable IDs, persisted entity
cards, normalized Measurement extraction, `KGStore` no-op interface. **No graph.**

**Phase 2 (first real KG):** AssertionMapper, SQLite store, `kg_write`, retroactive
`kg_build`, invariant tests, basic visualization, coarse Method tagging.

**Phase 3:** `kg_lookup` context cards, staleness + re-verification policy, A/B eval.

**Postponed to Phase 4 or indefinitely:** embedding/ML entity resolution, ontology languages
(RDF/OWL), Neo4j or any served graph infrastructure, cross-domain alignment, belief
aggregation/truth scoring (deliberately never: Determine reports disagreement, it does not
adjudicate science), temporal modeling beyond append-only history, multi-user access.

---

## Appendix — every architectural change, justified

| # | Change | Why needed | MVP? | Modifies | New component | Connecting interface / data structure |
|---|---|---|---|---|---|---|
| 1 | Stable global IDs (claims, passages, entities, computations) | Graph identity + cross-run linking; also improves audit trail | **Yes** | Run-state schema (M5/orchestration) | — | ID conventions in run-state JSON |
| 2 | Entity cards stored structured | Entity nodes + ER aliases for free from existing GROUND step | **Yes** | Planner (GROUND output format) | — | `entity_cards[]` field in state |
| 3 | Unit-normalized Measurement extraction | Measurement identity key requires canonical units | **Yes** (already designed; add normalization) | Claim decomposer (M3) | — | `claim.quantity` with pint-canonical unit |
| 4 | `KGStore` interface (no-op in MVP) | Lets Phases 2–4 swap backends without pipeline changes | **Yes** (interface only) | — | `kg/store.py` | `commit / find_entity / claims_for / verdict_history / neighbors` |
| 5 | AssertionMapper | Deterministic, LLM-free translation run state → assertions; unit-testable heart of the KG | Phase 2 | — | `kg/mapper.py` | `map(run_state) → [Assertion]` |
| 6 | `kg_write` LangGraph node | Live graphing of each completed run, off critical path | Phase 2 | LangGraph graph (adds terminal node) | node fn wrapping mapper+store | state fields `kg_assertions`, `kg_write_status` |
| 7 | Reified assertions w/ provenance | Traceability of every graph fact to run/evidence/model; append-only history | Phase 2 | — | Assertion dataclass + store schema | assertion JSON (§4) |
| 8 | Verdict as node + verdict history | Re-verification over time without overwriting; "science changes" representable | Phase 2 | Verdict handling (was terminal output only) | Verdict node type | `has_verdict` edges ordered by timestamp |
| 9 | `conflicts_with` + coexisting measurements | Explicit contradiction/uncertainty; no fact-collapsing | Phase 2 | — | edge type + creation rules in mapper | verifier output + `same_as` closure |
| 10 | Coarse Method tagging | `obtained_using` edges; the one new extraction | Phase 2 | GATHER evidence table (adds a tag column) | closed method vocabulary per domain | `evidence_row.method_tag` |
| 11 | `kg_lookup` node + context cards | Reuse of verified knowledge in future queries | Phase 3 | Planner input; answerer context (never verifier) | node fn + card renderer | `kg_context[]` state field |
| 12 | Staleness + re-verification policy | Stored verdicts must not become ground truth | Phase 3 | Plan gate (may inject re-verify GATHER step) | policy config | `staleness` on context cards; new Verdict nodes |
| 13 | ER beyond deterministic matching | Only if alias-miss rate proves material | Phase 4 | `same_as` creation | embedding matcher | unchanged (`same_as` edges) |

---

*Summary of the division of labor, restated once: LangGraph is the reasoning engine — it
decides what to retrieve, compute, verify, and when to give up. The knowledge graph is the
lab notebook that never forgets — a provenance-complete, append-only record of every claim
Determine has checked, every measurement it has extracted, every computation it has run, and
every verdict it has issued, contradictions and all.*
