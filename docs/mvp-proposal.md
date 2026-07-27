# Determine — MVP Proposal (filled-in decisions)

**Author:** prepared for Di Liu · **Date:** 2026-07-24 · **Status:** proposal for sign-off

---

## 0 · Decisions already fixed (input to this proposal)

- **MVP = the thinnest complete loop:** question → cited answer → atomic claims → per-claim
  verdicts → faithfulness score. Abstracts only, **hep-ph**, ~10 demo questions, retrieval
  deliberately dumb at first (BM25 only; hybrid/dense/rerank arrive in the measured Phase-1
  comparison, not in the MVP critical path).
- **Numeric checker is in the MVP** (§6).

Everything below is a recommendation with a default answer; each section ends with the
decision to confirm or override.

---

## 1 · How the framework breaks complex hep-ph queries into tasks

Decomposition happens **twice**, at two different places, serving two different masters.
Keeping them separate is a core design point:

| | Stage A — Planner | Stage B — Claim decomposer |
|---|---|---|
| When | before answering | after the draft answer exists |
| Input | the user's question | the cited answer text |
| Output | typed research plan (3–6 steps) | atomic, checkable claims |
| Optimizes for | building a good answer | verification granularity |

### 1.1 Stage A — Planner: question → typed research plan

The planner LLM decomposes the question into an ordered, shallow DAG of steps drawn from a
**closed taxonomy of five step types** (closed so behavior is testable and prompts stay small):

1. **GROUND** — pin down entities and conventions before anything is retrieved: which
   anomaly, which observable, which parameter space, which convention. In hep-ph this step
   is where most ambiguity lives (e.g. sin²2θ_ee vs sin²2θ_14; which flux model defines
   "the anomaly"; MS-bar vs pole mass). Output: an entity card per object
   `{name, aliases, defining convention, canonical parameters}` used to seed later queries.
2. **GATHER** — one focused evidence-collection sub-question per step, with 2–4 retrieval
   query seeds (aliases from GROUND expand the seeds). Output: an evidence table
   `{paper id, abstract span, reported quantity/claim}`.
3. **COMPUTE** — a derivable number the answer will need: unit conversions, ratios,
   tension-in-σ between two measurements, simple error propagation. Flagged
   `needs_computation: true` **with stated reasoning**, so the router later sends it to the
   numeric checker rather than to text entailment.
4. **COMPARE** — synthesis across GATHER/COMPUTE outputs: do regions overlap, do
   measurements agree, does an exclusion cover a preferred region.
5. **CONCLUDE** — assemble the cited answer under the cite-or-abstain contract, using only
   material committed by earlier steps.

**Every step carries an explicit contract** (the "typed steps with a contract" idea from the
original plan, made concrete):

```json
{
  "id": "S4", "type": "COMPUTE",
  "goal": "Quantify whether Neutrino-4's best-fit point lies inside the exclusion ranges quoted by PROSPECT/STEREO",
  "inputs": ["S2", "S3"],
  "retrieval_seeds": [],
  "needs_computation": {"flag": true,
    "reasoning": "requires comparing (Δm², sin²2θ) values and a significance estimate, not text entailment"},
  "deliverable": "in/out statement per experiment + tension in σ where uncertainties are quoted",
  "rubric": ["uses only numbers present in the evidence table", "states assumptions"]
}
```

**Plan-review gate** (rule-based first, LLM second):

- Rule checks (pure code, no LLM): DAG is acyclic; every GATHER has seeds; every
  quantitative deliverable is fed by a COMPUTE step; CONCLUDE depends on every other step;
  plan length 3–6 for MVP.
- One LLM review pass → `accepted` or one bounded revision (max 1, then accept-with-warning;
  never an unbounded loop — see §5).

Execution is sequential for the MVP, writing results into a running **notebook** (accumulated
evidence tables + committed step results), which becomes the context for CONCLUDE.

### 1.2 Worked decompositions (hep-ph)

**Q1 — "Do current reactor experiments rule out the sterile-neutrino explanation of the
reactor antineutrino anomaly?"**

- S1 GROUND: define the RAA; the sterile explanation's preferred region (eV-scale Δm²₄₁,
  sin²2θ_ee ≈ 0.05–0.15 under Huber–Mueller); note the flux-model dependence (re-evaluated
  fluxes shrink the anomaly itself). Entity cards: RAA, Neutrino-4, PROSPECT, STEREO, DANSS,
  flux models.
- S2 GATHER: exclusion results reported by PROSPECT, STEREO, DANSS (abstract-level regions
  and confidence levels).
- S3 GATHER: the Neutrino-4 claimed signal and published criticisms of its analysis.
- S4 COMPUTE (`needs_computation`): is the Neutrino-4 best fit (Δm² ≈ 7.3 eV², sin²2θ ≈ 0.36)
  inside the quoted exclusions; tension in σ where quotable.
- S5 COMPARE: what parameter space survives; how flux re-evaluations change the question
  ("is there still an anomaly to explain?").
- S6 CONCLUDE: cited answer; expected honest shape is "largely excluded under X, with the
  caveat that…" — hedges preserved as hedges.

**Q2 — "Is the CDF II W-mass measurement consistent with the SM electroweak fit and with
other measurements?"**

- S1 GROUND: CDF II value ± uncertainty; SM global-fit prediction ± uncertainty; competing
  measurements (ATLAS, LHCb) — entity cards with numbers slots to be filled by S2.
- S2 GATHER: the reported values (this question is deliberately numeric-heavy).
- S3 COMPUTE: pairwise tensions in σ (CDF vs SM fit, CDF vs ATLAS) with naive uncorrelated
  error combination, assumption stated.
- S4 COMPARE: consistency picture across measurements.
- S5 CONCLUDE.

**Q3 — "What does the lattice HVP result imply for the muon g−2 discrepancy?"**

- S1 GROUND: (g−2)_μ experimental average; data-driven vs lattice HVP as *two conventions
  for the SM prediction* — the GROUND step is exactly where this question is usually
  mangled.
- S2 GATHER: lattice (BMW-type) results; S3 GATHER: data-driven consensus and experiment.
- S4 COMPUTE: discrepancy in σ under each SM-prediction convention.
- S5 COMPARE: "the discrepancy is convention-dependent" synthesis; S6 CONCLUDE.

These three patterns (exclusion-vs-claim, measurement-vs-prediction, convention-conflict)
cover most complex hep-ph questions; simple factual questions degenerate gracefully to
GROUND → GATHER → CONCLUDE, which is the planner's minimum plan.

### 1.3 Stage B — Claim decomposer: answer → atomic claims

- An **atomic claim** is a single-predicate, decontextualized statement (entities resolved,
  no pronouns, no cross-sentence references) that a domain reader could check against
  literature in isolation.
- Each claim is **typed**: `report` ("PROSPECT excludes X at 95% CL"), `numeric` (carries a
  structured quantity `{quantity, value, unit, uncertainty, relation}`), `comparative`
  ("A is in tension with B at n σ"), `hedged` (the hedge is part of the claim — verified as
  "evidence suggests X", not as "X").
- Each claim keeps pointers to its source sentences and the citations those sentences carried
  — used for provenance display only, **never shown to the verifier** (§3).
- `numeric` and `comparative` claims are routed to **both** the retrieval verifier and the
  numeric checker; agreement/disagreement between the two is recorded.

### 1.4 Candidate MVP demo-question set (10, for your sanity-check)

Chosen to be answerable at abstract level, stable, and to mix step-type coverage. Two are
deliberately chosen to stress abstention. All in the neutrino/EW/BSM corner of hep-ph where
you can eyeball correctness:

1. Do current reactor experiments rule out the sterile-neutrino explanation of the reactor
   antineutrino anomaly? *(exclusion-vs-claim)*
2. Is the CDF II W-boson mass measurement consistent with the SM electroweak fit and other
   measurements? *(numeric tension)*
3. What does the lattice HVP calculation imply for the muon g−2 discrepancy?
   *(convention-conflict)*
4. Did the 2022 LHCb update of R(K) and R(K*) remove the evidence for lepton-flavor
   universality violation in b→sℓℓ decays? *(binary, clean)*
5. Has the XENON1T electron-recoil excess been confirmed or excluded? *(binary, clean)*
6. What sterile-neutrino parameter space remains viable for the gallium anomaly after the
   BEST experiment? *(quantitative survey)*
7. Is the MiniBooNE low-energy excess explained by an eV-scale sterile neutrino, given
   MicroBooNE results? *(multi-experiment synthesis)*
8. Does a ~95 GeV Higgs-like diphoton excess persist consistently across CMS and ATLAS
   analyses? *(comparative, likely NEI-heavy — abstention stress test)*
9. What are the strongest collider limits on GeV-scale heavy neutral leptons?
   *(survey; tests GATHER breadth)*
10. Do LHC results exclude natural weak-scale supersymmetry? *(broad, contested framing —
    abstention/hedging stress test)*

---

## 2 · Verdict contract (frozen before code)

- **Labels:** exactly `SUPPORTED / REFUTED / NOT-ENOUGH-EVIDENCE`, matching SciFact so the
  Phase-3 benchmark needs no label mapping. Conflicting evidence across sources is **NEI with
  a `conflict` reason code** and both quotes attached — not a fourth label (keeps MVP metrics
  simple; a CONFLICTING label can be split out later without re-annotating, since the reason
  code preserves the information).
- **Semantics are report-level, not truth-level:** SUPPORTED means *entailed by the retrieved
  literature*, REFUTED means *contradicted by it*. Determine never claims metaphysical truth
  — this phrasing also protects the demo when the literature itself is wrong.
- **Evidence scope:** a verdict must cite ≥1 specific passage; SUPPORTED/REFUTED require a
  **verbatim quote that is programmatically checked to be a substring of the passage**
  (cheap, deterministic anti-hallucination guard — reject and retry if the check fails).
  Entailment may use the union of top-k passages, but each quoted span is anchored.
- **Faithfulness score:** headline = `#SUPPORTED / #claims` (strict). Always reported as the
  full triple (S%, R%, NEI%) plus claim count — a 0.92 headline with 8% REFUTED and one with
  8% NEI are very different answers, and the strict score keeps the incentive honest
  (abstention at answer level is a feature; NEI at claim level still costs score, so the
  answerer is rewarded for not over-claiming).
- **Confidence:** verifier emits low/medium/high per verdict; logged, not used in the MVP
  score formula.

**Decision to confirm:** 3 labels, strict score, quote-substring guard.

---

## 3 · Model independence

A verifier built on the same model as the answerer tends to reproduce the answerer's own
reasoning and blind spots — independence of *evidence* is not independence of *judgment*.
Determine separates both:

- **Evidence independence (already in the plan):** the verifier runs fresh retrieval per
  claim; it never sees the answerer's passages or citations.
- **Model independence (new, explicit):** the verifier uses a **different model family** from
  the answerer. Recommended MVP casting: strong hosted model for answering + planner
  (e.g. Claude Sonnet-class); a different vendor's model or an open-weight model
  (via Hugging Face) for verification; a small cheap model for decomposition. Exact picks are
  a config entry, not an architecture question — the requirement is `answerer.family ≠
  verifier.family`, asserted in code at startup.
- **Blinding:** the verifier receives the bare decontextualized claim + its own retrieved
  evidence. No answer text, no reasoning, no citation list.
- **Auditability:** `model_per_role` recorded in every persisted run state; the demo can show
  "answered by A, checked by B".
- The DeBERTa-NLI baseline stays a Phase-3 comparison (not MVP), but it is the ultimate
  independence backstop: a deterministic non-generative check.

**Decision to confirm:** different-family constraint enforced in config.

---

## 4 · Evaluation design under fallible ground truth

Reference answers and benchmark gold labels are themselves fallible — human-annotated
datasets contain labeling errors, and auto-generated references can be inconsistent with
their own problem statements. Determine's evaluation is therefore designed so that no single
ground truth is load-bearing:

- **Primary controlled metric — hallucination injection (small version already in MVP):**
  take the 10 demo answers, programmatically corrupt ~20 claims (negate a relation, perturb
  a number ×2/×10, swap an entity/experiment name), re-run only the verifier, report
  detection rate + false-alarm rate on untouched claims. You control the ground truth, so
  this number is unimpeachable. Full 50-injection version in Phase 3.
- **SciFact is Phase 3, but its interface constraint lands now:** the verifier signature is
  `verify(claim, retriever) → verdict` — **corpus-agnostic**, with the retriever passed in.
  SciFact evaluation plugs in SciFact's own corpus; the MVP plugs in the hep-ph index. This
  is a day-one interface decision that costs nothing now and prevents a Phase-3 rewrite.
- **Disagreement-with-gold protocol:** when Determine disagrees with a SciFact gold label
  (or your eye disagrees with a demo verdict), the case is manually adjudicated and logged in
  an errata table — never silently counted, never used to tune prompts on the eval split.
  (Expect a nonzero errata table; it is demo material, not embarrassment.)
- **Benchmark hygiene** (from the original plan, kept): SciFact strictly held out from
  prompt development.

**Decision to confirm:** mini-injection test (~20 claims) included in MVP definition-of-done.

---

## 5 · Loop control and failure states

A known failure mode of agent pipelines is the silent stall: a run that nominally walks its
whole plan yet emits no usable result, because a disputed intermediate step blocked the
commit path. Determine's invariant is the opposite — every run degrades loudly and legibly:

- **Every claim terminates in exactly one of** `SUPPORTED`, `REFUTED`, or
  `NEI(reason_code)`, where reason ∈ {`no_evidence`, `conflict`, `budget_exhausted`,
  `tool_error`}. "Nothing" is not a representable outcome.
- **Budgets (MVP defaults):** ≤2 retrieval reformulations per claim; ≤2 numeric-checker
  iterations (1 generation + 1 reflection-driven fix); ≤1 plan revision; per-run wall-clock
  cap (default 5 min) and token cap. Exhaustion degrades to `NEI(budget_exhausted)` — a
  verdict, not a crash.
- **Run-level status:** `complete` | `partial` (some claims NEI(tool_error), all claims still
  have verdicts) | `failed` (exception; state persisted up to the failure point with a
  stored traceback).
- **Persisted state schema (append-only JSON per run), designed now:**
  `{run_id, question, config_hash, corpus_version, model_per_role, plan[steps{contract,
  status, committed_result}], notebook, retrieval_log[{step/claim, queries, passage_ids,
  scores}], answer{text, sentence→citation map}, claims[{text, type, source_sentences,
  quantity?, verdict{label, reason?, quotes[], confidence, model, iterations}}],
  score{S,R,NEI,headline}, timings, status}`.
  This schema *is* the audit trail, the debug tool, and the demo backend (the clickable
  trail renders straight from it) — three consumers, one artifact.

**Decision to confirm:** budgets above as defaults in config.

---

## 6 · Numeric checker — now in the MVP (scoped tightly)

Tool-verified computation is one of the strongest quality mechanisms an agent can have: an
LLM can hallucinate arithmetic, but it cannot hallucinate past an actual execution. Determine
includes a bounded, Python-native compute-and-reflect loop, scoped to claim checking rather
than open-ended problem solving:

- **MVP scope — four check types only:** unit conversions (via `pint`); ratios/percentages;
  arithmetic combinations of quantities quoted in the evidence; tension-in-σ between two
  values with quoted uncertainties (uncorrelated combination, assumption recorded).
  Anything beyond this → the checker declines (`not_checkable`) and the claim falls back to
  text entailment alone. Declining is correct behavior, not failure.
- **Pipeline:** numeric-claim detector (rule-based number/unit extraction + LLM type tag) →
  structured quantities → LLM generates a short Python/SymPy/pint check script → sandboxed
  execution (no network, timeout 10 s) → tolerance comparison (relative 5% default; σ-based
  when uncertainties exist) → result recorded as `computation` evidence on the claim.
- **Reflect loop, hard-capped:** one critique pass on the generated script, one fix, then
  commit whatever exists (per §5 — no silent stalls).
- **Verdict fusion:** computation and retrieval evidence are recorded separately. If they
  disagree, the claim is `NEI(conflict)` with both shown — disagreement between literature
  and arithmetic is exactly what Determine exists to surface, so it is displayed, not
  averaged away.

---

## 7 · Practicalities (recommended defaults)

- **Models & budget:** strong hosted model for answer/planner, different-family model for
  verification (§3), small model for decomposition and iteration loops. Aggressive caching
  keyed on `(model, prompt_hash)`. Soft budget cap for the whole MVP build: ~US$50 of API
  usage; the cache makes re-runs nearly free.
- **Corpus:** one-shot arXiv harvest of hep-ph abstracts (~5–10k, e.g. 2015→present for the
  neutrino/EW slice), respecting arXiv API rate etiquette; raw responses stored; a
  `corpus_version` hash (harvest date + query) recorded in every run state so evaluations
  are reproducible. Semantic Scholar API key requested early (free tier, but approval takes
  days) — MVP works from arXiv alone if it hasn't arrived.
- **Repo scaffold:** `src/determine/{corpus, retrieve, answer, decompose, verify, compute,
  orchestrate, eval}`, pydantic-settings config, pytest with unit tests for the pure-code
  guards (quote-substring check, plan rule-gate, verdict-totality), GitHub Actions running
  lint + unit tests, fixed seeds. LangGraph for orchestration per the original plan.
- **MVP definition of done (checklist):**
  1. 10 demo questions run end-to-end, each producing a persisted run state;
  2. every claim in every run carries a terminal verdict (invariant test passes);
  3. numeric checker fires on ≥1 claim in ≥3 questions;
  4. mini injection test (~20 corrupted claims) with detection + false-alarm rates reported;
  5. one script regenerates every number in the results table from the persisted states.

---

## 8 · Open items deliberately left out of the MVP

Hybrid/dense retrieval comparison (Phase 1 measurement, after the loop works); SciFact +
NLI baseline (Phase 3); re-ranker, full-text PDFs, multi-domain, Streamlit polish (Phase 4);
answer *revision* after REFUTED verdicts (post-MVP — the MVP only reports; self-correction
of the answer is a second loop worth doing carefully).
