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
  config.py        settings incl. budgets + independence assertion
  corpus/          arXiv harvester (JSONL corpus, versioned)
  retrieve/        BM25 retriever behind the corpus-agnostic Retriever protocol
  answer/          grounded answerer (cite-or-abstain)            [stub]
  decompose/       Stage-B atomic claim decomposer                [stub]
  verify/          blind verifier + pure-code quote guard
  compute/         numeric checker (4 check types, declines rest)
  orchestrate/     pipeline nodes + LangGraph graph
  eval/            hallucination-injection test + metrics
  kg/              KGStore interface (no-op in MVP)
questions/         the 10 hep-ph demo questions
runs/              persisted run states (one JSON per run)
```

## Quickstart

```bash
pip install -e ".[dev]"
pytest                                   # invariants, guards, dry-run pipeline
determine run "What is the W boson mass?"   # dry-run end-to-end on the sample corpus
determine fetch --max-results 5000          # harvest the real hep-ph corpus (Phase 1)
```

The scaffold ships in `dry_run=True` mode: the full pipeline runs end-to-end with zero LLM
calls and deterministic stub output, producing a real persisted run state. Set
`DETERMINE_DRY_RUN=false` plus API keys in `.env` as the LLM nodes land.

## Build status (Phase 0)

- [x] Package scaffold, config, budgets, independence assertion
- [x] Run-state schema with verdict-totality invariant + strict score
- [x] BM25 retrieval over JSONL corpus; arXiv harvester
- [x] Pipeline skeleton (sequential + LangGraph) running end-to-end in dry-run
- [x] Quote-substring guard; injection corruptions + detection metrics
- [x] KGStore no-op interface (KG-ready per plan v2)
- [ ] LLM planner / answerer / decomposer / verifier (build Phase 1–2)
- [ ] Live numeric checker; 10-question demo runs; mini injection test
