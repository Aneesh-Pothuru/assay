from __future__ import annotations

import html
import json
from pathlib import Path

from .core import Comparison
from .schemas.loopkit import Run


def write_demo_report(
    path: Path, baseline: Run, candidate: Run, comparison: Comparison
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "baseline_run": baseline.run_id,
        "candidate_run": candidate.run_id,
        "dataset_hash": baseline.dataset_hash,
        "scorer_hash": baseline.scorer_hash,
        "comparison": comparison.to_dict(),
    }
    json_path = path.with_name("comparison.json")
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    rows = "\n".join(
        f"<tr><td>{html.escape(sample_id)}</td><td>1.000</td><td>0.000</td></tr>"
        for sample_id in comparison.regressions
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASSAY demo — {comparison.verdict.value}</title>
<style>
body{{font:16px/1.5 system-ui;max-width:920px;margin:3rem auto;padding:0 1rem;color:#18202a}}
.verdict{{display:inline-block;padding:.35rem .7rem;border-radius:.4rem;background:#8b1e2d;color:white;font-weight:700}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:2rem 0}}
.card{{border:1px solid #d8dee7;border-radius:.6rem;padding:1rem}} table{{border-collapse:collapse;width:100%}}
th,td{{border-bottom:1px solid #ddd;text-align:left;padding:.5rem}} code{{font-size:.8rem;word-break:break-all}}
</style></head><body>
<p>ASSAY / deterministic bundled replay</p>
<h1>Per-sample regression report</h1>
<p class="verdict">{comparison.verdict.value}</p>
<div class="cards">
<div class="card"><strong>Baseline</strong><br>{comparison.baseline:.3f}</div>
<div class="card"><strong>Candidate</strong><br>{comparison.candidate:.3f}</div>
<div class="card"><strong>Delta</strong><br>{comparison.delta:+.3f}</div>
</div>
<p>95% paired CI: [{comparison.ci_low:+.3f}, {comparison.ci_high:+.3f}].
Method: {html.escape(comparison.method)}. {len(comparison.regressions)} of
100 samples regressed; no aggregate-only verdict.</p>
<p><small>Dataset <code>{html.escape(baseline.dataset_hash)}</code><br>
Scorer <code>{html.escape(baseline.scorer_hash)}</code></small></p>
<h2>Regressed samples</h2>
<table><thead><tr><th>Sample</th><th>Before</th><th>After</th></tr></thead>
<tbody>{rows}</tbody></table>
<p>This page is generated from a synthetic fixture and makes no
real-provider performance claim. See LIMITS.md.</p>
</body></html>
"""
    path.write_text(document)

