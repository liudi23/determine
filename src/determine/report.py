"""Auditable report renderer — run state JSON → self-contained HTML.

Usage:  determine report            # latest run
        determine report r_ab12cd   # specific run
Renders the answer with citations, the score triple, every claim with its verdict,
verbatim quotes, computation results, and the full retrieval log — nothing hidden.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

BADGE = {
    "SUPPORTED": ("#0a7f3f", "#e7f6ec"),
    "REFUTED": ("#b00020", "#fdecea"),
    "NOT-ENOUGH-EVIDENCE": ("#8a6d00", "#fff8e1"),
}

CSS = """
body{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;max-width:900px;
margin:2rem auto;padding:0 1rem;color:#1a1a2e;line-height:1.55}
h1{font-size:1.5rem} h2{font-size:1.15rem;margin-top:2rem;border-bottom:1px solid #ddd;
padding-bottom:.3rem} .muted{color:#667;font-size:.85rem}
.badge{display:inline-block;padding:.1rem .55rem;border-radius:1rem;font-size:.8rem;
font-weight:600} .score{font-size:1.05rem;margin:.8rem 0}
.claim{border:1px solid #e3e3ee;border-radius:8px;padding:.8rem 1rem;margin:.8rem 0}
.quote{background:#f6f6fb;border-left:3px solid #99c;padding:.4rem .8rem;margin:.5rem 0;
font-style:italic;font-size:.92rem} code{background:#f2f2f7;padding:.05rem .3rem;
border-radius:4px;font-size:.85rem} details{margin:.6rem 0}
summary{cursor:pointer;color:#446} table{border-collapse:collapse;font-size:.85rem}
td,th{border:1px solid #e0e0ea;padding:.3rem .6rem;text-align:left}
"""


def _badge(label: str) -> str:
    fg, bg = BADGE.get(label, ("#555", "#eee"))
    return f'<span class="badge" style="color:{fg};background:{bg}">{html.escape(label)}</span>'


def render_html(state: dict) -> str:
    e = html.escape
    s = state.get("score", {})
    parts = [f"<html><head><meta charset='utf-8'><title>Determine — {e(state['run_id'])}"
             f"</title><style>{CSS}</style></head><body>"]
    parts.append(f"<h1>Determine report</h1><p class='muted'>run <code>{e(state['run_id'])}"
                 f"</code> · status <b>{e(state.get('status', '?'))}</b> · corpus "
                 f"<code>{e(state.get('corpus_version', '?'))}</code> · models: "
                 + ", ".join(f"{e(k)}=<code>{e(v)}</code>"
                             for k, v in state.get("model_per_role", {}).items())
                 + "</p>")
    parts.append(f"<h2>Question</h2><p>{e(state.get('question', ''))}</p>")

    parts.append("<h2>Faithfulness score</h2>"
                 f"<p class='score'><b>{s.get('headline', 0):.2f}</b> — "
                 f"{s.get('supported', 0)} supported · {s.get('refuted', 0)} refuted · "
                 f"{s.get('nei', 0)} not-enough-evidence "
                 f"(of {sum(s.get(k, 0) for k in ('supported', 'refuted', 'nei'))} claims)</p>")

    parts.append("<h2>Answer</h2><p>" + e(state.get("answer", {}).get("text", "")) + "</p>")
    cites = state.get("answer", {}).get("sentence_citations", {})
    if cites:
        parts.append("<details><summary>sentence → citations</summary><table>"
                     "<tr><th>#</th><th>cited passages</th></tr>")
        for i, pids in sorted(cites.items(), key=lambda kv: int(kv[0])):
            parts.append(f"<tr><td>{i}</td><td>{', '.join(f'<code>{e(p)}</code>' for p in pids) or '—'}</td></tr>")
        parts.append("</table></details>")

    parts.append("<h2>Claims &amp; verdicts</h2>")
    for c in state.get("claims", []):
        v = c.get("verdict") or {}
        parts.append(f"<div class='claim'><p>{_badge(v.get('label', '?'))} "
                     f"<span class='muted'>[{e(c.get('type', ''))}]</span> {e(c['text'])}</p>")
        if v.get("reason"):
            parts.append(f"<p class='muted'>reason: {e(v['reason'])}</p>")
        for q in v.get("quotes", []):
            parts.append(f"<div class='quote'>“{e(q)}”</div>")
        if v.get("passage_ids"):
            parts.append("<p class='muted'>evidence: "
                         + ", ".join(f"<code>{e(p)}</code>" for p in v["passage_ids"])
                         + f" · confidence {e(v.get('confidence', '?'))}"
                         + f" · verifier <code>{e(v.get('model', '?'))}</code></p>")
        comp = c.get("computation")
        if comp:
            parts.append(f"<p class='muted'>computation [{e(comp.get('status', ''))}]: "
                         f"{e(comp.get('output', ''))}</p>")
        parts.append("</div>")

    log = state.get("retrieval_log", [])
    parts.append(f"<h2>Retrieval log</h2><details><summary>{len(log)} search(es) — "
                 "every query the pipeline ran, including verifier reformulations</summary>"
                 "<table><tr><th>for</th><th>query</th><th># hits</th></tr>")
    for r in log:
        for q in r.get("queries", []):
            parts.append(f"<tr><td><code>{e(r.get('for_id', ''))}</code></td>"
                         f"<td>{e(q)}</td><td>{len(r.get('passage_ids', []))}</td></tr>")
    parts.append("</table></details>")

    parts.append("<h2>Plan</h2><table><tr><th>id</th><th>type</th><th>goal</th></tr>")
    for st in state.get("plan", []):
        parts.append(f"<tr><td>{e(st['id'])}</td><td>{e(st['type'])}</td>"
                     f"<td>{e(st['goal'])}</td></tr>")
    parts.append("</table>")

    parts.append("<p class='muted'>Generated by Determine — an answer engine that is also "
                 "its own fact-checker. Full machine-readable state: "
                 f"<code>runs/{e(state['run_id'])}.json</code></p></body></html>")
    return "".join(parts)


def report_run(runs_dir: str = "runs", run_id: str | None = None) -> Path:
    runs = sorted(Path(runs_dir).glob("r_*.json"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit(f"no runs found in {runs_dir}/")
    path = (Path(runs_dir) / f"{run_id}.json") if run_id else runs[-1]
    if not path.exists():
        raise SystemExit(f"run not found: {path}")
    state = json.loads(path.read_text())
    out = path.with_suffix(".html")
    out.write_text(render_html(state))
    return out
