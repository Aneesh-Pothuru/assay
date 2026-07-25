from __future__ import annotations

import json
from pathlib import Path

from .core import Comparison
from .schemas.loopkit import Run


def _script_safe_json(value: object) -> str:
    """Serialize untrusted report data without allowing an inline-script escape."""
    return (
        json.dumps(value, separators=(",", ":"), sort_keys=True)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


APP_SHELL = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Run a deterministic ASSAY evaluation and inspect the evidence behind the merge gate.">
  <meta name="theme-color" content="#eef7fa">
  <title>ASSAY bench · evaluation evidence</title>
  <link rel="stylesheet" href="app.css">
</head>
<body>
  <a class="skip-link" href="#bench">Skip to the evaluation bench</a>
  <header class="app-header">
    <a class="wordmark" href="../" aria-label="ASSAY home">
      <span class="wordmark-mark" aria-hidden="true">A</span>
      <span>ASSAY<small>evaluation laboratory</small></span>
    </a>
    <div class="run-identity">
      <span class="live-pip" aria-hidden="true"></span>
      <span id="header-status">Replay mode · embedded fixture</span>
      <a href="../#method">Protocol 01</a>
    </div>
  </header>

  <main id="bench">
    <section class="bench-heading" aria-labelledby="bench-title">
      <div>
        <p class="kicker">CI specimen / deterministic replay</p>
        <h1 id="bench-title">Model change assay</h1>
        <p>Pair two version-pinned runs. Expose the uncertainty. Decide whether
          the evidence permits a merge. This Pages build replays embedded data;
          it does not call the installed local service.</p>
      </div>
      <div class="bench-stamp">
        <span>ASSAY NO.</span>
        <strong>A-0012</strong>
        <span>100 paired samples</span>
      </div>
    </section>

    <aside class="replay-banner" aria-label="Replay mode disclosure">
      <div><strong>STATIC REPLAY</strong><span>Browser-only interaction over deterministic fixtures</span></div>
      <p>For persisted user runs and the real HTTP/CLI path, install the package
        and run <code>assay serve --seed-demo</code>.</p>
      <a href="https://github.com/Aneesh-Pothuru/assay/blob/main/docs/OPERATIONS.md">Local service operations ↗</a>
    </aside>

    <section class="lab-layout">
      <aside class="protocol-panel" aria-labelledby="protocol-title">
        <div class="panel-tab"><span>01</span> protocol</div>
        <h2 id="protocol-title">Prepare the run</h2>
        <p class="panel-intro">Choose a controlled fixture, comparison pair, and
          allowed regression before starting the assay.</p>
        <p class="fixture-note">The default tool-selection comparison is generated
          by the Python reference implementation. Alternate controls are labeled,
          deterministic interaction fixtures.</p>

        <form id="run-form">
          <label for="suite">Evaluation suite</label>
          <select id="suite" name="suite">
            <option value="prod-agents">Production agents · 100 samples</option>
            <option value="tool-critical">Tool-critical slice · 40 samples</option>
            <option value="world-core">World-model core · 64 rollouts</option>
          </select>

          <div class="field-pair">
            <div>
              <label for="baseline">Baseline</label>
              <select id="baseline" name="baseline">
                <option value="model-v1">main / model-v1</option>
                <option value="model-v0">release / model-v0</option>
              </select>
            </div>
            <div>
              <label for="candidate">Candidate</label>
              <select id="candidate" name="candidate">
                <option value="prompt-v2">PR #482 / prompt-v2</option>
                <option value="tool-v3">PR #509 / tool-router-v3</option>
                <option value="stable-v2">PR #521 / stable-v2</option>
                <option value="scorer-drift">PR #533 / scorer-v2 · incompatible</option>
              </select>
            </div>
          </div>

          <label for="scorer">Versioned scorer</label>
          <select id="scorer" name="scorer">
            <option value="accuracy">exact_tool_selection@1.0.0</option>
            <option value="grounding">wm/action_grounding@0.1.0</option>
            <option value="memory">wm/occlusion_memory@0.1.0</option>
          </select>

          <div class="tolerance-head">
            <label for="tolerance">Allowed regression</label>
            <output id="tolerance-value" for="tolerance">0.00</output>
          </div>
          <input id="tolerance" type="range" min="0" max="0.20" value="0" step="0.01">
          <div class="range-scale"><span>strict</span><span>0.20 lenient</span></div>

          <div class="protocol-actions">
            <button class="primary-action" type="submit" id="run-button">
              <span>Run full assay</span><kbd>R</kbd>
            </button>
            <button class="secondary-action" type="button" id="step-button">Step protocol</button>
            <button class="text-action" type="button" id="reset-button">Reset</button>
          </div>
        </form>

        <div class="pin-card">
          <div><span>Dataset pin</span><code id="dataset-pin">loading</code></div>
          <div><span>Required scorer pin</span><code id="scorer-pin">loading</code></div>
          <div id="candidate-pin-row"><span>Candidate scorer pin</span><code id="candidate-scorer-pin">loading</code></div>
        </div>
      </aside>

      <div class="analysis-column">
        <section class="process-card" aria-labelledby="process-title">
          <div class="panel-tab"><span>02</span> process</div>
          <div class="process-head">
            <div>
              <h2 id="process-title">Evidence pipeline</h2>
              <p id="process-copy">Awaiting a run. No verdict has been issued.</p>
            </div>
            <div class="sample-vial" aria-hidden="true"><i id="vial-fill"></i></div>
          </div>
          <ol class="process-steps" id="process-steps">
            <li data-step="0"><span>1</span><b>Pin</b><small>dataset + scorer</small></li>
            <li data-step="1"><span>2</span><b>Replay</b><small>paired samples</small></li>
            <li data-step="2"><span>3</span><b>Score</b><small>same contract</small></li>
            <li data-step="3"><span>4</span><b>Infer</b><small>95% paired CI</small></li>
            <li data-step="4"><span>5</span><b>Gate</b><small>merge verdict</small></li>
          </ol>
          <div class="chromatogram" aria-label="Run progress">
            <div class="chrom-track"><i id="chrom-progress"></i></div>
            <div class="chrom-labels"><span>inoculate</span><span>separate</span><span>read</span></div>
          </div>
        </section>

        <section class="result-grid" aria-live="polite">
          <article class="measurement-card">
            <span class="measure-label">Baseline mean</span>
            <strong id="baseline-score">—</strong>
            <div class="measure-rule blue"><i id="baseline-bar"></i></div>
            <small id="baseline-name">model-v1</small>
          </article>
          <article class="measurement-card">
            <span class="measure-label">Candidate mean</span>
            <strong id="candidate-score">—</strong>
            <div class="measure-rule red"><i id="candidate-bar"></i></div>
            <small id="candidate-name">prompt-v2</small>
          </article>
          <article class="measurement-card">
            <span class="measure-label">Paired delta</span>
            <strong id="delta-score">—</strong>
            <div class="ci-readout"><span id="ci-low">—</span><i></i><span id="ci-high">—</span></div>
            <small>95% confidence interval</small>
          </article>
          <article class="verdict-card" id="verdict-card">
            <span class="measure-label">Merge decision</span>
            <strong id="verdict">NOT RUN</strong>
            <p id="verdict-reason">Run the protocol to produce a verdict.</p>
            <button type="button" id="recover-button" hidden>Use compatible pins</button>
            <span class="proof-mark" aria-hidden="true">UNREAD</span>
          </article>
        </section>

        <section class="chart-card" aria-labelledby="chart-title">
          <div class="section-head">
            <div>
              <div class="panel-tab"><span>03</span> uncertainty</div>
              <h2 id="chart-title">Score and confidence evolution</h2>
            </div>
            <div class="chart-legend" aria-label="Chart legend">
              <span><i class="blue-dot"></i> baseline</span>
              <span><i class="red-dot"></i> candidate</span>
              <span><i class="band-key"></i> 95% CI</span>
            </div>
          </div>
          <div class="chart-wrap">
            <canvas id="score-chart" width="1000" height="330"
              aria-label="Line chart of baseline and candidate scores as samples are processed"></canvas>
            <div class="chart-empty" id="chart-empty">Start or step the protocol to develop the trace.</div>
          </div>
          <p class="chart-note">The interval uses the implementation’s paired normal approximation.
            It is not a claim of universal statistical validity.</p>
        </section>
      </div>
    </section>

    <section class="sample-lab" aria-labelledby="samples-title">
      <div class="section-head">
        <div>
          <div class="panel-tab"><span>04</span> specimens</div>
          <h2 id="samples-title">Paired sample plate</h2>
          <p>Each well is one matched example. Select a well to inspect its input,
            expected output, prediction, and exact score transition.</p>
        </div>
        <div class="filter-set" role="group" aria-label="Filter samples">
          <button class="filter active" type="button" data-filter="all">All <span id="all-count">100</span></button>
          <button class="filter" type="button" data-filter="regressed">Regressed <span id="regressed-count">0</span></button>
          <button class="filter" type="button" data-filter="held">Held <span id="held-count">0</span></button>
          <button class="filter" type="button" data-filter="improved">Improved <span id="improved-count">0</span></button>
        </div>
      </div>

      <div class="sample-workspace">
        <div class="plate-wrap">
          <div class="plate-labels" aria-hidden="true"><span>A</span><span>B</span><span>C</span><span>D</span><span>E</span></div>
          <div class="sample-plate" id="sample-plate" aria-label="Selectable sample wells"></div>
          <div class="plate-legend">
            <span><i class="well-legend held"></i> held</span>
            <span><i class="well-legend regressed"></i> regressed</span>
            <span><i class="well-legend improved"></i> improved</span>
            <span><i class="well-legend pending"></i> pending</span>
          </div>
        </div>

        <aside class="specimen-drawer" id="specimen-drawer" aria-labelledby="specimen-title">
          <div class="drawer-head">
            <div>
              <span class="eyebrow">Specimen record</span>
              <h3 id="specimen-title">Select a sample</h3>
            </div>
            <span class="specimen-status" id="specimen-status">UNREAD</span>
          </div>
          <dl class="specimen-meta">
            <div><dt>Slice</dt><dd id="sample-slice">—</dd></div>
            <div><dt>Score</dt><dd id="sample-score">—</dd></div>
          </dl>
          <div class="specimen-field">
            <span>Input</span>
            <code id="sample-input">Choose any well to open its paired evidence.</code>
          </div>
          <div class="diff-columns">
            <div><span>Expected / baseline</span><code id="sample-before">—</code></div>
            <div><span>Candidate</span><code id="sample-after">—</code></div>
          </div>
          <p class="drawer-note" id="sample-note">Aggregate scores cannot explain a failure. The specimen can.</p>
        </aside>
      </div>
    </section>

    <section class="evidence-footer" aria-labelledby="evidence-title">
      <div>
        <div class="panel-tab"><span>05</span> chain of custody</div>
        <h2 id="evidence-title">Package the evidence</h2>
        <p>Export the structured comparison or copy a review-ready summary.
          The bundle includes the run IDs, hashes, interval, changed samples,
          tolerance, and verdict.</p>
      </div>
      <div class="evidence-actions">
        <button type="button" id="copy-button" disabled>Copy review note</button>
        <button type="button" id="export-button" disabled>Export evidence.json</button>
      </div>
      <p class="toast" id="toast" role="status"></p>
    </section>
  </main>

  <footer class="app-footer">
    <span>Static deterministic replay · no backend or provider claim</span>
    <nav aria-label="Footer">
      <a href="../#evidence">Proof</a>
      <a href="../#limits">Limits</a>
      <a href="comparison.json">Raw comparison</a>
      <a href="https://github.com/Aneesh-Pothuru/assay/blob/main/docs/OPERATIONS.md">Live path</a>
      <a href="https://github.com/Aneesh-Pothuru/assay">Source</a>
    </nav>
  </footer>

  <script>window.ASSAY_DATA = __ASSAY_DATA__;</script>
  <script src="app.js"></script>
</body>
</html>
"""


def write_demo_report(
    path: Path, baseline: Run, candidate: Run, comparison: Comparison
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_by_id = {sample.sample_id: sample for sample in candidate.samples}
    paired_samples = []
    for before in sorted(baseline.samples, key=lambda sample: sample.sample_id):
        after = candidate_by_id[before.sample_id]
        paired_samples.append(
            {
                "sample_id": before.sample_id,
                "context": before.context,
                "reference": before.reference,
                "baseline_prediction": before.prediction,
                "candidate_prediction": after.prediction,
                "baseline_score": before.scores[comparison.metric],
                "candidate_score": after.scores[comparison.metric],
            }
        )
    data = {
        "baseline_run": baseline.run_id,
        "candidate_run": candidate.run_id,
        "dataset_hash": baseline.dataset_hash,
        "scorer_hash": baseline.scorer_hash,
        "comparison": comparison.to_dict(),
        "samples": paired_samples,
        "scope": (
            "Bundled deterministic fixture. No real-provider, public-checkpoint, "
            "latency, cost, or nondeterminism claim."
        ),
    }
    json_path = path.with_name("comparison.json")
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    serialized = _script_safe_json(data)
    path.write_text(APP_SHELL.replace("__ASSAY_DATA__", serialized))
