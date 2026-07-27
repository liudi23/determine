# Determine

**A scientific claim-verification agent: retrieve → reason → verify → score.**
*"LLMs sound convincing even when they're wrong. Determine finds out whether they're right."*

An answer engine that is also its own fact-checker: it drafts literature-grounded, cited
answers, decomposes them into atomic claims, independently verifies every claim against
fresh evidence (and re-computes the numbers), and reports an auditable faithfulness score.

## Architecture

```
Question
  → Research planning        GROUND / GATHER / COMPUTE / COMPARE / CONCLUDE  (+ plan gate)
  → Scientific retrieval     BM25 over hep-ph abstracts (hybrid later, measured)
  → Grounded answer          cite-or-abstain; every sentence carries [doc:chunk] citations
  → Atomic claims            typed: report / numeric / comparative / hedged
  → Verification ∥ Compute   blind verifier (different model family, fresh retrieval)
                             ∥ numeric checker (pint/SymPy, sandboxed, hard-capped loop)
  → Verdicts                 SUPPORTED / REFUTED / NEI(reason) — totality enforced
  → KG write                 no-op in MVP; Phase 2 persists a provenance-complete graph
  → Auditable report         score triple (S/R/NEI) + clickable evidence trail
```

Design principles (see `determine-mvp-proposal.md` / `determine-plan-v2.md` for the full
plan): verification first; independence of evidence **and** of judgment
(`answerer.family != verifier.family`, asserted at startup); ground everything groundable;
every run persists a complete JSON audit state; measure, don't claim.

## Layout

```
src/determine/
  schema.py        run-state schema: claims, verdicts, invariants (single source of truth)
  config.py        settings: budgets, model-per-role casting, independence assertion
  llm/             vendor-agnostic LLM clients (Anthropic + OpenAI), disk cache, JSON parsing
  corpus/          arXiv harvester (JSONL corpus, versioned)
  retrieve/        BM25 retriever behind the corpus-agnostic Retriever protocol
  answer/          grounded answerer (cite-or-abstain, sentence-level citations)
  decompose/       Stage-B atomic claim decomposer (typed claims + structured quantities)
  verify/          blind verifier (fresh retrieval, quote guard, budgets) + pure-code guards
  compute/         numeric checker (deterministic v1: quantity vs evidence quotes)
  orchestrate/     planner (Stage-A typed plans) + pipeline nodes + LangGraph graph
  eval/            hallucination-injection test + metrics
  kg/              KGStore interface (no-op in MVP; graph lands in Phase 2 of the v2 plan)
docs/              MVP proposal + project plan v2 (knowledge-graph extension)
questions/         the 10 hep-ph demo questions
scripts/           check_keys.py — zero-cost API-key verification
runs/              persisted run states (one JSON per run)
```

## Quickstart

```bash
bash quickstart.sh                       # venv (Python >= 3.11) → install → tests → dry run
```

or step by step:

```bash
pip install -e ".[dev]"
pytest                                   # invariants, guards, JSON/cache utils, dry-run pipeline
determine run "What is the W boson mass?"   # dry-run end-to-end on the sample corpus
```

Going live:

```bash
cp .env.example .env                     # add ANTHROPIC_API_KEY and OPENAI_API_KEY
python scripts/check_keys.py             # zero-cost auth check for both vendors
determine fetch --max-results 5000       # one-shot hep-ph abstract harvest (versioned)
# set DETERMINE_DRY_RUN=false in .env, then:
determine run --corpus data/corpus/hepph.jsonl "your hep-ph question"
```

Model casting (config defaults; verified against the account's model lists): answerer /
planner / decomposer `claude-sonnet-5`; verifier `gpt-5.6-luna` (dev) or `gpt-5.6-terra`
(scored runs). The independence constraint — answerer and verifier from different model
families — is asserted at startup, and every run records `model_per_role` in its state.

## Build status

**Phase 0 — scaffold (done)**

- [x] Package scaffold, config, budgets, independence assertion
- [x] Run-state schema with verdict-totality invariant + strict score
- [x] BM25 retrieval over JSONL corpus; arXiv harvester
- [x] Pipeline skeleton (sequential + LangGraph) running end-to-end in dry-run
- [x] Quote-substring guard; injection corruptions + detection metrics
- [x] KGStore no-op interface (KG-ready per plan v2)

**Phase 1 — live pipeline (code complete, first live runs in progress)**

- [x] LLM client layer: Anthropic + OpenAI, retries, disk cache keyed on (model, prompt hash)
- [x] Live planner (typed GROUND/GATHER/COMPUTE/COMPARE/CONCLUDE plans, JSON contract)
- [x] Live answerer (cite-or-abstain, sentence citations, clean abstention on empty retrieval)
- [x] Live blind verifier (fresh retrieval, quote guard with retry, bounded reformulation)
- [x] Numeric checker v1 (deterministic quantity-vs-quote comparison, 5% tolerance)
- [ ] hep-ph corpus harvested; first live run inspected
- [ ] 10-question demo runs with persisted states
- [ ] Mini hallucination-injection test (~20 corrupted claims) with detection/false-alarm rates
- [ ] Numeric checker v2 (LLM-generated pint/SymPy check scripts, sandboxed)
