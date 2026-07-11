#!/usr/bin/env python3
"""Build the public Billie Flow bake-off artifact."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
VOCABULARY = ["Wispr Flow", "Billie Flow", "LLM", "MacBook"]


def e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_seconds(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}s"
    except (TypeError, ValueError):
        return e(value)


def fmt_score(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.0f}/5"
    except (TypeError, ValueError):
        return e(value)


def slug(value: str | None) -> str:
    return (value or "").replace("_", "-").lower()


def by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item.get("id"): item for item in items}


def defaults(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("evaluations", {}).get("recommended_defaults", {})


def style_by_id(data: dict[str, Any], item_id: str | None) -> dict[str, Any] | None:
    if not item_id:
        return None
    for item in data.get("style_results", []):
        if item.get("id") == item_id:
            return item
    return None


def score_meter(value: Any, invert: bool = False) -> str:
    if value is None:
        return '<span class="muted">n/a</span>'
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return e(value)
    bounded = max(0.0, min(5.0, numeric))
    if invert:
        bounded = 5.0 - bounded
    pct = int((bounded / 5.0) * 100)
    return (
        '<span class="meter">'
        f'<span class="meter-track"><span style="width:{pct}%"></span></span>'
        f"<span>{fmt_score(value)}</span>"
        "</span>"
    )


def status_label(status: str | None) -> str:
    if status == "complete":
        return "ran"
    if status in {"blocked", "failed"}:
        return status
    return status or "unknown"


def branch_role(item: dict[str, Any], data: dict[str, Any]) -> str:
    default = defaults(data)
    item_id = item.get("id")
    if item_id == default.get("default_asr_backend"):
        return "default"
    if item_id == default.get("fallback_asr_backend"):
        return "smoke"
    if item_id in set(default.get("lab_only_asr_backends", [])):
        return "lab"
    if item.get("status") != "complete":
        return "blocked"
    return "candidate"


def term_findings(data: dict[str, Any], asr_id: str | None) -> list[dict[str, Any]]:
    for item in data.get("evaluations", {}).get("vocabulary_failures", []):
        if item.get("asr_id") == asr_id:
            return item.get("findings", [])
    return []


def highlight_evidence(text: str, findings: list[dict[str, Any]]) -> str:
    escaped = e(text)
    replacements: list[tuple[str, str]] = []
    for finding in findings:
        term = finding.get("term")
        if term and finding.get("status") == "correct":
            replacements.append((term, f'<mark class="ok">{e(term)}</mark>'))
        for observed in finding.get("observed_errors", []):
            if observed:
                replacements.append((observed, f'<mark class="bad">{e(observed)}</mark>'))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    for raw, replacement in replacements:
        escaped = escaped.replace(e(raw), replacement)
    return escaped


def text_sample(text: str, findings: list[dict[str, Any]] | None = None) -> str:
    return f'<div class="sample-text">{highlight_evidence(text, findings or [])}</div>'


def list_items(items: list[str]) -> str:
    if not items:
        return '<p class="muted">None recorded.</p>'
    return "<ul>" + "".join(f"<li>{e(item)}</li>" for item in items) + "</ul>"


def correction_text(corrections: list[dict[str, Any]]) -> str:
    if not corrections:
        return "No deterministic correction recorded."
    return ", ".join(
        f"{item.get('from')} -> {item.get('to')} ({item.get('count')})"
        for item in corrections
    )


def shared_chrome() -> tuple[str, str]:
    header_path = SHARED / "site-header.html"
    css_path = SHARED / "site-chrome.css"
    if header_path.exists() and css_path.exists():
        return (
            header_path.read_text(encoding="utf-8").strip(),
            css_path.read_text(encoding="utf-8").strip(),
        )
    return (
        '<header class="site-header" data-billiem-chrome="site-header">'
        '<a class="wordmark" href="https://billiem.uk/" aria-label="billiem home">billiem</a>'
        '<nav aria-label="Site"><a href="https://billiem.uk/feed.xml">RSS</a>'
        '<a href="https://billiem.uk/graph/">Graph</a>'
        '<a href="https://github.com/billiem" rel="me noopener noreferrer">GitHub</a></nav></header>',
        fallback_chrome_css(),
    )


def render_intro(data: dict[str, Any]) -> str:
    run = data.get("run", {})
    default = defaults(data)
    asr_map = by_id(data.get("asr_results", []))
    default_asr = asr_map.get(default.get("default_asr_backend"), {})
    default_style = style_by_id(data, default.get("default_combination_id")) or {}
    completed_asr = sum(1 for item in data.get("asr_results", []) if item.get("status") == "complete")
    cleanup_count = sum(1 for item in data.get("style_results", []) if item.get("status") == "complete")
    return f"""
    <section class="intro report-intro" aria-labelledby="report-title">
      <p class="eyebrow">Billie Flow Lab</p>
      <h1 id="report-title">{e(run.get("title", "Voice Memo ASR Bake-off"))}</h1>
      <p class="lede">Use MLX Whisper large-v3-turbo for the first app default, pair it with small local light cleanup, and keep vocabulary correction deterministic.</p>
      <dl class="summary-strip">
        <div><dt>Clip</dt><dd>{fmt_seconds(run.get("duration_seconds"))}</dd></div>
        <div><dt>ASR default</dt><dd>{e(default_asr.get("label", default.get("default_asr_backend", "n/a")))}</dd></div>
        <div><dt>Cleanup</dt><dd>{e(default_style.get("cleanup_model_label", default.get("default_cleanup_model", "n/a")))}</dd></div>
        <div><dt>Evidence</dt><dd>{completed_asr} ASR branches, {cleanup_count} cleanup runs</dd></div>
      </dl>
    </section>
    """


def render_branch_diagram(data: dict[str, Any]) -> str:
    rows = []
    for item in data.get("asr_results", []):
        role = branch_role(item, data)
        findings = term_findings(data, item.get("id"))
        correct_terms = sum(1 for finding in findings if finding.get("status") == "correct")
        missed_terms = len(findings) - correct_terms
        rows.append(
            f"""
            <article class="branch-row branch-{e(role)}">
              <div class="branch-role">{e(role)}</div>
              <div class="branch-node">
                <span>chunking</span>
                <strong>{e(item.get("chunking_strategy", "unknown"))}</strong>
              </div>
              <div class="branch-node">
                <span>ASR</span>
                <strong>{e(item.get("label", item.get("id")))}</strong>
                <small>{e(status_label(item.get("status")))} / {fmt_seconds(item.get("runtime_seconds"))}</small>
              </div>
              <div class="branch-node">
                <span>vocabulary</span>
                <strong>{correct_terms} correct / {missed_terms} missed</strong>
              </div>
              <div class="branch-verdict">{e(item.get("review", {}).get("summary", "No review recorded."))}</div>
            </article>
            """
        )
    return f"""
    <section class="evidence-section" id="diagram">
      <div class="section-head">
        <div>
          <p class="eyebrow">branch map</p>
          <h2>One memo, five routes through the pipeline</h2>
        </div>
        <p class="small">The page stays diagram-first; transcripts sit behind the model rows.</p>
      </div>
      <div class="pipeline-spine" aria-label="Pipeline">
        <span>Voice memo</span>
        <span>16 kHz mono</span>
        <span>ASR branch</span>
        <span>Cleanup</span>
        <span>Vocabulary repair</span>
      </div>
      <div class="branch-list">{''.join(rows)}</div>
    </section>
    """


def render_asr_evidence(data: dict[str, Any]) -> str:
    cards = []
    for item in data.get("asr_results", []):
        findings = term_findings(data, item.get("id"))
        review = item.get("review", {})
        scores = review.get("scores", {})
        cards.append(
            f"""
            <details class="model-evidence">
              <summary>
                <span>
                  <strong>{e(item.get("label", item.get("id")))}</strong>
                  <em>{e(branch_role(item, data))} / {fmt_seconds(item.get("runtime_seconds"))}</em>
                </span>
                <span>{score_meter(scores.get("accuracy"))}</span>
              </summary>
              <div class="evidence-grid">
                <div>
                  <h3>What it heard</h3>
                  {text_sample(item.get("stitched_transcript", ""), findings)}
                </div>
                <div>
                  <h3>Read</h3>
                  <p>{e(review.get("summary", "No review recorded."))}</p>
                  <h3>Weaknesses</h3>
                  {list_items(review.get("weaknesses", []))}
                </div>
              </div>
            </details>
            """
        )
    return f"""
    <section class="evidence-section" id="asr-evidence">
      <div class="section-head">
        <div>
          <p class="eyebrow">ASR evidence</p>
          <h2>Click into the transcript only when the summary is not enough</h2>
        </div>
      </div>
      <div class="model-list">{''.join(cards)}</div>
    </section>
    """


def render_defaults(data: dict[str, Any]) -> str:
    default = defaults(data)
    recommendations = data.get("recommendations", [])
    rec_html = "".join(
        f"""
        <article class="recommendation rec-{e(item.get("level", "note"))}">
          <span>{e(item.get("level", "note"))}</span>
          <strong>{e(item.get("title", "Untitled"))}</strong>
          <p>{e(item.get("body", ""))}</p>
        </article>
        """
        for item in recommendations
    )
    return f"""
    <section class="evidence-section" id="defaults">
      <div class="section-head">
        <div>
          <p class="eyebrow">decision</p>
          <h2>The first app default is already clear enough</h2>
        </div>
      </div>
      <dl class="decision-grid">
        <div><dt>ASR</dt><dd>{e(default.get("default_asr_backend", "n/a"))}</dd></div>
        <div><dt>Cleanup model</dt><dd>{e(default.get("default_cleanup_model", "n/a"))}</dd></div>
        <div><dt>Style</dt><dd>{e(default.get("default_cleanup_style", "n/a"))}</dd></div>
        <div><dt>Fallback</dt><dd>{e(default.get("fallback_asr_backend", "n/a"))}<small>{e(default.get("fallback_note", ""))}</small></dd></div>
      </dl>
      <div class="recommendation-grid">{rec_html}</div>
    </section>
    """


def cleanup_pick(data: dict[str, Any], asr_id: str, model_id: str, style_id: str) -> dict[str, Any] | None:
    for item in data.get("style_results", []):
        if (
            item.get("source_asr_id") == asr_id
            and item.get("cleanup_model_id") == model_id
            and item.get("style_id") == style_id
        ):
            return item
    return None


def curated_cleanup(data: dict[str, Any]) -> list[dict[str, Any]]:
    default = defaults(data)
    picks: list[dict[str, Any]] = []
    default_item = style_by_id(data, default.get("default_combination_id"))
    if default_item:
        picks.append(default_item)
    candidate_specs = [
        ("mlx-whisper-large-v3-turbo", "mlx-local-small-text", "verbatim-context-corrected"),
        ("mlx-whisper-large-v3-turbo", "mlx-local-small-text", "notes"),
        ("mlx-whisper-tiny", "mlx-local-small-text", "light-cleanup"),
        ("gemma-4-12b-audio", "mlx-local-small-text", "light-cleanup"),
    ]
    seen = {item.get("id") for item in picks}
    for asr_id, model_id, style_id in candidate_specs:
        item = cleanup_pick(data, asr_id, model_id, style_id)
        if item and item.get("id") not in seen:
            seen.add(item.get("id"))
            picks.append(item)
    return picks[:5]


def render_cleanup_examples(data: dict[str, Any]) -> str:
    cards = []
    for item in curated_cleanup(data):
        review = item.get("review", {})
        scores = review.get("scores", {})
        cards.append(
            f"""
            <article class="cleanup-example">
              <div class="cleanup-meta">
                <span>{e(item.get("source_asr_label", item.get("source_asr_id")))}</span>
                <strong>{e(item.get("style_label", item.get("style_id")))} / {e(item.get("cleanup_model_label", item.get("cleanup_model_id")))}</strong>
              </div>
              <p>{e(review.get("summary", "No review recorded."))}</p>
              <div class="score-line">
                <span>fidelity {score_meter(scores.get("fidelity"))}</span>
                <span>voice {score_meter(scores.get("voice_preservation"))}</span>
                <span>invention {score_meter(scores.get("invention_risk"), invert=True)}</span>
              </div>
              {text_sample(item.get("output", ""))}
              <p class="correction-line">{e(correction_text(item.get("postprocess_corrections", [])))}</p>
            </article>
            """
        )
    return f"""
    <section class="evidence-section" id="cleanup">
      <div class="section-head">
        <div>
          <p class="eyebrow">cleanup examples</p>
          <h2>Enough style evidence to judge the default, not seventy cards</h2>
        </div>
      </div>
      <div class="cleanup-list">{''.join(cards)}</div>
    </section>
    """


def render_vocab_matrix(data: dict[str, Any]) -> str:
    asr_items = data.get("asr_results", [])
    header = "".join(f"<th>{e(term)}</th>" for term in VOCABULARY)
    rows = []
    for asr in asr_items:
        findings = {finding.get("term"): finding for finding in term_findings(data, asr.get("id"))}
        cells = []
        for term in VOCABULARY:
            finding = findings.get(term, {})
            if finding.get("status") == "correct":
                cells.append('<td><span class="term-ok">correct</span></td>')
            else:
                observed = ", ".join(finding.get("observed_errors", [])) or "missed"
                cells.append(f'<td><span class="term-bad">{e(observed)}</span></td>')
        rows.append(
            f"""
            <tr>
              <th scope="row">{e(asr.get("label", asr.get("id")))}</th>
              {''.join(cells)}
            </tr>
            """
        )
    return f"""
    <section class="evidence-section" id="vocabulary">
      <div class="section-head">
        <div>
          <p class="eyebrow">vocabulary</p>
          <h2>The product names are the real test</h2>
        </div>
      </div>
      <div class="table-wrap vocab-wrap">
        <table>
          <thead><tr><th>Model</th>{header}</tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <p class="small">The app default should expose raw ASR, model cleanup, and final corrected text in debug mode so this repair layer stays visible.</p>
    </section>
    """


def render_methodology(data: dict[str, Any]) -> str:
    blocked = data.get("evaluations", {}).get("setup_findings", [])
    blockers = data.get("evaluations", {}).get("cleanup_model_blockers", [])
    notes = [
        "The source was a 35.3 second Voice Memos clip normalized to 16 kHz mono.",
        "ASR and cleanup were evaluated as separate stages so polished text could not hide transcription errors.",
        "Gemma, Voxtral, and Parakeet are useful lab evidence, but their runtimes and vocabulary misses keep them out of the first default.",
        "Raw runner files are local lab evidence and are not embedded in this public artifact.",
    ]
    blocked_rows = "".join(
        f"<li>{e(item.get('id'))}: {e(item.get('summary'))}</li>"
        for item in blocked
    )
    blocker_rows = "".join(
        f"<li>{e(item.get('cleanup_model_label', item.get('cleanup_model_id')))}: {e('; '.join(item.get('errors', [])))}</li>"
        for item in blockers
    )
    return f"""
    <section class="evidence-section" id="method">
      <div class="section-head">
        <div>
          <p class="eyebrow">method</p>
          <h2>Small enough to audit, not a benchmark claim</h2>
        </div>
      </div>
      <div class="method-grid">
        <div>{list_items(notes)}</div>
        <div>
          <h3>Setup notes kept visible</h3>
          <ul>{blocked_rows}{blocker_rows}</ul>
        </div>
      </div>
    </section>
    """


def fallback_chrome_css() -> str:
    return """
:root {
  color-scheme: light dark;
  --bg: #f7f7f4;
  --ink: #18181b;
  --muted: #6d6d74;
  --line: #d8d8d2;
  --panel: #ffffff;
  --accent: #7c6bd9;
  --accent-soft: #ece8ff;
  --mark: #eeebff;
  --code: #eeeeea;
  --measure: 70ch;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f0f11;
    --ink: #f2f2f0;
    --muted: #a0a0a8;
    --line: #303034;
    --panel: #17171a;
    --accent: #c0b4ff;
    --accent-soft: #242033;
    --mark: #262238;
    --code: #1c1c20;
  }
}
* { box-sizing: border-box; }
html {
  background: var(--bg);
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.62;
}
body { margin: 0; }
.site-header, .site-width { width: min(100% - 2rem, 58rem); margin-inline: auto; }
.site-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-block: 1.15rem 2.25rem;
  font-size: 0.92rem;
}
.wordmark { font-size: 1.12rem; font-weight: 780; letter-spacing: 0; text-decoration: none; }
.site-header nav { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.7rem 1rem; }
.site-header nav a { color: var(--muted); text-decoration: none; }
a { color: inherit; text-decoration-color: var(--accent); text-underline-offset: 0.18em; }
"""


def page_css() -> str:
    return """
main {
  width: min(100% - 2rem, 58rem);
  margin-inline: auto;
}
h1, h2, h3 {
  font-weight: 760;
  line-height: 1.08;
  letter-spacing: 0;
}
h1 {
  max-width: 13ch;
  margin: 0;
  font-size: clamp(2.4rem, 9vw, 6.6rem);
}
h2 {
  margin: 0;
  font-size: clamp(1.35rem, 3.6vw, 2.05rem);
}
h3 {
  margin: 0 0 0.4rem;
  font-size: 1rem;
}
p {
  max-width: var(--measure);
}
.report-intro {
  max-width: 56rem;
  padding-block: 1rem 2rem;
  border-bottom: 1px solid var(--line);
}
.eyebrow,
.small,
dt,
small {
  color: var(--muted);
  font-size: 0.88rem;
}
.eyebrow {
  margin: 0 0 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}
.lede {
  max-width: 48rem;
  color: var(--muted);
  font-size: clamp(1.1rem, 2.5vw, 1.45rem);
}
.summary-strip,
.decision-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  margin: 1.4rem 0 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.summary-strip div,
.decision-grid div {
  min-width: 0;
  padding: 0.85rem 1rem 0.85rem 0;
  border-right: 1px solid var(--line);
}
.summary-strip div:last-child,
.decision-grid div:last-child {
  border-right: 0;
}
dt {
  margin: 0 0 0.2rem;
}
dd {
  margin: 0;
  font-weight: 760;
  overflow-wrap: anywhere;
}
dd small {
  display: block;
  margin-top: 0.2rem;
  font-weight: 400;
}
.evidence-section {
  padding-block: 2rem;
  border-bottom: 1px solid var(--line);
}
.section-head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}
.section-head p {
  margin: 0;
}
.pipeline-spine {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.pipeline-spine span,
.branch-node,
.recommendation,
.cleanup-example,
.model-evidence {
  border: 1px solid var(--line);
  background: color-mix(in srgb, var(--panel) 82%, var(--bg));
}
.pipeline-spine span {
  padding: 0.55rem 0.65rem;
  color: var(--muted);
  font-size: 0.82rem;
}
.branch-list,
.model-list,
.cleanup-list,
.recommendation-grid {
  display: grid;
  gap: 0.7rem;
}
.branch-row {
  display: grid;
  grid-template-columns: 5.2rem repeat(3, minmax(0, 1fr)) minmax(12rem, 1.35fr);
  gap: 0.5rem;
  align-items: stretch;
}
.branch-role {
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 760;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.branch-default .branch-role,
.branch-default .branch-node {
  border-color: color-mix(in srgb, var(--accent) 65%, var(--line));
  background: var(--accent-soft);
}
.branch-node,
.branch-verdict {
  min-width: 0;
  padding: 0.7rem;
}
.branch-node span,
.cleanup-meta span,
.recommendation span {
  display: block;
  color: var(--muted);
  font-size: 0.76rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.branch-node strong,
.cleanup-meta strong {
  display: block;
  overflow-wrap: anywhere;
}
.branch-node small {
  display: block;
  margin-top: 0.2rem;
}
.branch-verdict {
  color: var(--muted);
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.decision-grid {
  margin-bottom: 1rem;
}
.recommendation-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.recommendation,
.cleanup-example {
  padding: 1rem;
}
.recommendation strong {
  display: block;
  margin-top: 0.2rem;
}
.recommendation p,
.cleanup-example p {
  margin-block: 0.45rem 0;
  color: var(--muted);
}
.model-evidence {
  overflow: hidden;
}
.model-evidence summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 1rem;
  cursor: pointer;
}
.model-evidence summary strong,
.model-evidence summary em {
  display: block;
}
.model-evidence summary em {
  color: var(--muted);
  font-size: 0.86rem;
  font-style: normal;
}
.evidence-grid,
.method-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 0.9fr);
  gap: 1rem;
  padding: 1rem;
  border-top: 1px solid var(--line);
}
.sample-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  padding: 0.85rem;
  border: 1px solid var(--line);
  background: var(--code);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.86rem;
  line-height: 1.5;
}
mark {
  padding: 0 0.15rem;
  color: inherit;
}
mark.ok {
  background: color-mix(in srgb, #4d7c5e 20%, var(--mark));
}
mark.bad {
  background: color-mix(in srgb, #b65b5b 28%, var(--mark));
  outline: 1px solid color-mix(in srgb, #b65b5b 35%, transparent);
}
.score-line {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 1rem;
  margin: 0.75rem 0;
  color: var(--muted);
  font-size: 0.84rem;
}
.meter {
  display: inline-grid;
  grid-template-columns: 4.5rem 2.6rem;
  gap: 0.35rem;
  align-items: center;
}
.meter-track {
  height: 0.42rem;
  border-radius: 999px;
  background: var(--line);
  overflow: hidden;
}
.meter-track span {
  display: block;
  height: 100%;
  background: var(--accent);
}
.correction-line {
  font-size: 0.84rem;
}
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--line);
}
table {
  width: 100%;
  min-width: 48rem;
  border-collapse: collapse;
}
th,
td {
  padding: 0.75rem;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}
thead th {
  color: var(--muted);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
tr:last-child th,
tr:last-child td {
  border-bottom: 0;
}
.term-ok,
.term-bad {
  display: inline-block;
  padding: 0.08rem 0.36rem;
  border: 1px solid var(--line);
  font-size: 0.84rem;
}
.term-ok {
  background: color-mix(in srgb, #4d7c5e 18%, var(--panel));
}
.term-bad {
  background: color-mix(in srgb, #b65b5b 18%, var(--panel));
}
ul {
  margin: 0;
  padding-left: 1.1rem;
}
li + li {
  margin-top: 0.35rem;
}
footer {
  width: min(100% - 2rem, 58rem);
  margin-inline: auto;
  padding-block: 1.4rem 2.5rem;
  color: var(--muted);
  font-size: 0.86rem;
}
@media (max-width: 52rem) {
  .summary-strip,
  .decision-grid,
  .pipeline-spine,
  .branch-row,
  .recommendation-grid,
  .evidence-grid,
  .method-grid {
    grid-template-columns: 1fr;
  }
  .summary-strip div,
  .decision-grid div {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .summary-strip div:last-child,
  .decision-grid div:last-child {
    border-bottom: 0;
  }
  .section-head,
  .model-evidence summary {
    display: block;
  }
  .meter {
    margin-top: 0.45rem;
  }
}
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    transition: none !important;
    animation: none !important;
  }
}
"""


def render_page(data: dict[str, Any]) -> str:
    header_html, chrome_css = shared_chrome()
    run = data.get("run", {})
    title = run.get("title") or f"Billie Flow Report: {run.get('id', 'run')}"
    snapshot_date = str(run.get("created_at", "undated"))[:10]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{e(title)}</title>
  <style>
{chrome_css}
{page_css()}
  </style>
</head>
<body>
{header_html}
  <main>
    {render_intro(data)}
    {render_branch_diagram(data)}
    {render_defaults(data)}
    {render_asr_evidence(data)}
    {render_cleanup_examples(data)}
    {render_vocab_matrix(data)}
    {render_methodology(data)}
  </main>
  <footer>
    Evidence snapshot {e(snapshot_date)} from the cleaned Billie Flow Lab results. Raw runner files are intentionally not embedded in this public artifact.
  </footer>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Path to results.json")
    parser.add_argument("--output", required=True, type=Path, help="Path to write report HTML")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = "\n".join(line.rstrip() for line in render_page(data).splitlines()) + "\n"
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
