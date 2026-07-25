(() => {
  "use strict";

  const source = window.ASSAY_DATA;
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  const profiles = {
    "prompt-v2": { regressions: 12, improvements: 0, label: "prompt-v2", offset: 0 },
    "tool-v3": { regressions: 7, improvements: 3, label: "tool-router-v3", offset: 4 },
    "stable-v2": { regressions: 1, improvements: 4, label: "stable-v2", offset: 9 },
    "scorer-drift": {
      regressions: 0,
      improvements: 0,
      label: "scorer-v2",
      offset: 0,
      candidateScorerHash: "sha256:ac1475a500c006e513040ce310d6d60d4dbf53c89264da49fa0fa9bdc1cd3b4e"
    }
  };
  const baselineProfiles = {
    "model-v1": { additionalMisses: 0 },
    "model-v0": { additionalMisses: 5 }
  };
  const suiteSizes = { "prod-agents": 100, "tool-critical": 40, "world-core": 64 };
  const scorerLabels = {
    accuracy: "exact_tool_selection@1.0.0",
    grounding: "wm/action_grounding@0.1.0",
    memory: "wm/occlusion_memory@0.1.0"
  };
  const datasetPins = {
    "prod-agents": source.dataset_hash,
    "tool-critical": "sha256:36fd184b6d80832bde9455f67d0d9ae712794ec8969f6cfdc80324e0392f5a2b",
    "world-core": "sha256:a4487bd7b1489a79779e9652ceceea54e5734163efd952b42121d5f5fe4d1f9e"
  };
  const scorerPins = {
    accuracy: source.scorer_hash,
    grounding: "sha256:2903b343d7427f3c17e690864966800c6c406cba527abf1260d0373dd27a6d7e",
    memory: "sha256:e312195f22c01b6ccca280966ec9f6d39328cfe12c6d562595c81d2863d430c0"
  };

  const state = {
    phase: -1,
    running: false,
    timer: null,
    filter: "all",
    samples: [],
    result: null,
    contractError: false
  };

  function profile() {
    return profiles[$("#candidate").value];
  }

  function selectedSize() {
    return suiteSizes[$("#suite").value];
  }

  function contractIssue() {
    const candidateHash = profile().candidateScorerHash;
    const requiredHash = scorerPins[$("#scorer").value];
    if (!candidateHash || candidateHash === requiredHash) return null;
    return { candidateHash, requiredHash };
  }

  function buildSamples() {
    const count = selectedSize();
    const chosen = profile();
    const chosenBaseline = baselineProfiles[$("#baseline").value];
    const worldMode = $("#suite").value === "world-core";
    const base = source.samples.slice(0, count).map((sample, index) => {
      const rotated = (index + chosen.offset) % count;
      const regressed = rotated < Math.min(chosen.regressions, count);
      const baselineMisses = Math.min(chosen.improvements + chosenBaseline.additionalMisses, count);
      const improved = !regressed && rotated >= count - baselineMisses;
      const toolReference = index % 2 === 0 ? "search" : "lookup";
      const stateReference = `state(x=${index % 8}, y=${Math.floor(index / 8)}, h=${(index % 4) + 1})`;
      const reference = worldMode ? stateReference : toolReference;
      const alternate = worldMode
        ? `state(x=${(index + 1) % 8}, y=${Math.floor(index / 8)}, h=${(index % 4) + 1})`
        : (reference === "search" ? "lookup" : "search");
      return {
        id: sample.sample_id,
        index,
        input: worldMode
          ? `predict held-out state after action-${index % 4} at horizon ${(index % 4) + 1}`
          : `select tool for case ${String(index).padStart(3, "0")}`,
        slice: worldMode
          ? (index % 3 === 0 ? "wm / drift" : index % 3 === 1 ? "wm / grounding" : "wm / memory")
          : (index < 20 ? "tool-routing / edge" : index % 3 === 0 ? "tool-routing / multi-step" : "tool-routing / core"),
        reference,
        baseline: improved ? alternate : reference,
        candidate: regressed ? alternate : reference,
        before: improved ? 0 : 1,
        after: regressed ? 0 : 1,
        status: regressed ? "regressed" : improved ? "improved" : "held"
      };
    });
    state.samples = base;
  }

  function calculateResult(processed = selectedSize()) {
    const visible = state.samples.slice(0, processed);
    if (!visible.length) return null;
    const baseline = visible.reduce((sum, item) => sum + item.before, 0) / visible.length;
    const candidate = visible.reduce((sum, item) => sum + item.after, 0) / visible.length;
    const deltas = visible.map((item) => item.after - item.before);
    const delta = candidate - baseline;
    const mean = delta;
    const variance = deltas.length > 1
      ? deltas.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / (deltas.length - 1)
      : 0;
    const se = Math.sqrt(variance) / Math.sqrt(deltas.length);
    const ciLow = delta - 1.96 * se;
    const ciHigh = delta + 1.96 * se;
    const tolerance = Number($("#tolerance").value);
    return {
      baseline, candidate, delta, ciLow, ciHigh, tolerance,
      verdict: ciHigh < -tolerance ? "BLOCKED" : "PASSED",
      processed,
      regressions: visible.filter((item) => item.status === "regressed").map((item) => item.id),
      improvements: visible.filter((item) => item.status === "improved").map((item) => item.id)
    };
  }

  function fmt(value, signed = false) {
    if (!Number.isFinite(value)) return "—";
    return `${signed && value >= 0 ? "+" : ""}${value.toFixed(3)}`;
  }

  function renderPins() {
    $("#dataset-pin").textContent = datasetPins[$("#suite").value];
    const requiredHash = scorerPins[$("#scorer").value];
    const candidateHash = profile().candidateScorerHash || requiredHash;
    $("#scorer-pin").textContent = requiredHash;
    $("#candidate-scorer-pin").textContent = candidateHash;
    $("#candidate-pin-row").classList.toggle("mismatch", candidateHash !== requiredHash);
  }

  function renderPlate() {
    const plate = $("#sample-plate");
    plate.innerHTML = "";
    const hasResults = state.phase >= 2;
    state.samples.forEach((sample) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `sample-well ${hasResults ? sample.status : "pending"}`;
      button.dataset.status = hasResults ? sample.status : "pending";
      button.dataset.index = String(sample.index);
      button.setAttribute("aria-label", `${sample.id}: ${hasResults ? sample.status : "pending"}`);
      button.hidden = state.filter !== "all" && button.dataset.status !== state.filter;
      button.addEventListener("click", () => selectSample(sample.index));
      plate.appendChild(button);
    });
    $("#all-count").textContent = String(state.samples.length);
    $("#regressed-count").textContent = hasResults
      ? String(state.samples.filter((item) => item.status === "regressed").length) : "0";
    $("#held-count").textContent = hasResults
      ? String(state.samples.filter((item) => item.status === "held").length) : "0";
    $("#improved-count").textContent = hasResults
      ? String(state.samples.filter((item) => item.status === "improved").length) : "0";
  }

  function selectSample(index) {
    const sample = state.samples[index];
    $$(".sample-well").forEach((well) => well.classList.toggle("selected", Number(well.dataset.index) === index));
    $("#specimen-title").textContent = sample.id;
    $("#specimen-status").textContent = state.phase >= 2 ? sample.status.toUpperCase() : "PENDING";
    $("#sample-slice").textContent = sample.slice;
    $("#sample-score").textContent = state.phase >= 2 ? `${sample.before.toFixed(3)} → ${sample.after.toFixed(3)}` : "not scored";
    $("#sample-input").textContent = sample.input;
    $("#sample-before").textContent = `${sample.reference} / ${sample.baseline}`;
    $("#sample-after").textContent = state.phase >= 2 ? sample.candidate : "awaiting scoring";
    $("#sample-note").textContent = state.phase < 2
      ? "This specimen has not been scored. Advance the protocol before interpreting its outcome."
      : sample.status === "regressed"
      ? "Candidate changed the selected tool while the reference remained fixed. This sample contributes −1.000 to the paired delta."
      : sample.status === "improved"
        ? "Candidate corrected a baseline miss. This sample contributes +1.000 to the paired delta."
        : "The expected and candidate tools agree on this specimen.";
  }

  function updatePhase(nextPhase) {
    state.phase = Math.max(-1, Math.min(4, nextPhase));
    $$("#process-steps li").forEach((item, index) => {
      item.classList.toggle("complete", index < state.phase);
      item.classList.toggle("active", index === state.phase);
    });
    const percent = state.phase < 0 ? 0 : ((state.phase + 1) / 5) * 100;
    $("#chrom-progress").style.width = `${percent}%`;
    $("#vial-fill").style.height = `${percent}%`;
    const copy = [
      "Version pins sealed. The comparison contract is now immutable.",
      `Replayed ${selectedSize()} paired specimens from the controlled fixture.`,
      `Applied ${scorerLabels[$("#scorer").value]} to both runs.`,
      "Estimated the paired delta and 95% confidence interval.",
      "Gate issued. Inspect the specimens before accepting the decision."
    ];
    $("#process-copy").textContent = state.phase < 0 ? "Awaiting a run. No verdict has been issued." : copy[state.phase];
    $("#header-status").textContent = state.phase < 4 ? (state.phase < 0 ? "Ready for specimen" : `Protocol ${state.phase + 1} of 5`) : "Evidence package ready";
    if (state.phase >= 1) renderPlate();
    if (state.phase >= 2) updateMeasurements();
    if (state.phase >= 3) drawChart();
    if (state.phase >= 4) updateVerdict();
  }

  function updateMeasurements() {
    state.result = calculateResult();
    const result = state.result;
    $("#baseline-score").textContent = fmt(result.baseline);
    $("#candidate-score").textContent = fmt(result.candidate);
    $("#delta-score").textContent = fmt(result.delta, true);
    $("#ci-low").textContent = fmt(result.ciLow, true);
    $("#ci-high").textContent = fmt(result.ciHigh, true);
    $("#baseline-bar").style.width = `${result.baseline * 100}%`;
    $("#candidate-bar").style.width = `${result.candidate * 100}%`;
    $("#baseline-name").textContent = $("#baseline").selectedOptions[0].textContent;
    $("#candidate-name").textContent = $("#candidate").selectedOptions[0].textContent;
  }

  function updateVerdict() {
    state.result = calculateResult();
    const result = state.result;
    const card = $("#verdict-card");
    card.classList.remove("blocked", "passed");
    card.classList.add(result.verdict.toLowerCase());
    $("#verdict").textContent = result.verdict === "BLOCKED" ? "MERGE BLOCKED" : "MERGE PERMITTED";
    $("#verdict-reason").textContent = result.verdict === "BLOCKED"
      ? `CI high ${fmt(result.ciHigh, true)} is below the allowed −${result.tolerance.toFixed(2)} regression.`
      : `CI high ${fmt(result.ciHigh, true)} is at or above the allowed −${result.tolerance.toFixed(2)} regression boundary.`;
    $(".proof-mark").textContent = result.verdict;
    $("#recover-button").hidden = true;
    $("#copy-button").disabled = false;
    $("#export-button").disabled = false;
  }

  function renderContractError() {
    const issue = contractIssue();
    if (!issue) return false;
    updatePhase(0);
    state.contractError = true;
    state.result = null;
    state.running = false;
    $("#run-button").disabled = false;
    $("#header-status").textContent = "Contract error · merge withheld";
    $("#process-copy").textContent =
      "Pinning stopped: the candidate scorer hash differs from the required comparison contract. No replay, inference, or gate was performed.";
    const card = $("#verdict-card");
    card.classList.remove("blocked", "passed");
    card.classList.add("contract-error");
    $("#verdict").textContent = "MERGE WITHHELD";
    $("#verdict-reason").textContent =
      `Candidate ${issue.candidateHash.slice(0, 20)}… does not match required ${issue.requiredHash.slice(0, 20)}…. Cross-scorer comparison refused.`;
    $(".proof-mark").textContent = "CONTRACT ERROR";
    $("#recover-button").hidden = false;
    $("#copy-button").disabled = true;
    $("#export-button").disabled = true;
    return true;
  }

  function drawChart() {
    const canvas = $("#score-chart");
    const ctx = canvas.getContext("2d");
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.max(600, rect.width * ratio);
    canvas.height = 280 * ratio;
    ctx.scale(ratio, ratio);
    const width = canvas.width / ratio;
    const height = 280;
    const pad = { top: 24, right: 26, bottom: 34, left: 46 };
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, width, height);

    ctx.font = "10px Courier New";
    ctx.textAlign = "right";
    for (let tick = 0; tick <= 4; tick += 1) {
      const value = tick * 0.25;
      const y = pad.top + (4 - tick) * ((height - pad.top - pad.bottom) / 4);
      ctx.strokeStyle = "#d2cec2";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(width - pad.right, y);
      ctx.stroke();
      ctx.fillStyle = "#59616a";
      ctx.fillText(value.toFixed(2), pad.left - 8, y + 3);
    }

    const checkpoints = Array.from(
      new Set(Array.from({ length: 5 }, (_value, index) => Math.max(1, Math.round(selectedSize() * (index + 1) / 5))))
    );
    const points = checkpoints.map((count) => ({ count, ...calculateResult(count) }));
    const x = (index) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, points.length - 1));
    const y = (value) => pad.top + (1.0 - value) * (height - pad.top - pad.bottom);

    ctx.fillStyle = "rgba(214,52,44,.14)";
    ctx.beginPath();
    points.forEach((point, index) => {
      const upper = Math.min(1, point.baseline + point.ciHigh);
      const py = y(upper);
      if (index === 0) ctx.moveTo(x(index), py); else ctx.lineTo(x(index), py);
    });
    [...points].reverse().forEach((point, reverseIndex) => {
      const index = points.length - 1 - reverseIndex;
      const lower = Math.max(0, point.baseline + point.ciLow);
      ctx.lineTo(x(index), y(lower));
    });
    ctx.closePath();
    ctx.fill();

    function line(key, color) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.beginPath();
      points.forEach((point, index) => {
        const py = y(point[key]);
        if (index === 0) ctx.moveTo(x(index), py); else ctx.lineTo(x(index), py);
      });
      ctx.stroke();
      points.forEach((point, index) => {
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x(index), y(point[key]), 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      });
    }
    line("baseline", "#194bff");
    line("candidate", "#d6342c");

    ctx.textAlign = "center";
    ctx.fillStyle = "#59616a";
    points.forEach((point, index) => ctx.fillText(`n=${point.count}`, x(index), height - 12));
    $("#chart-empty").hidden = true;
  }

  function runFull() {
    if (state.running) return;
    reset(false);
    if (renderContractError()) return;
    state.running = true;
    $("#run-button").disabled = true;
    let phase = 0;
    updatePhase(phase);
    state.timer = window.setInterval(() => {
      phase += 1;
      updatePhase(phase);
      if (phase >= 4) {
        window.clearInterval(state.timer);
        state.running = false;
        $("#run-button").disabled = false;
      }
    }, 420);
  }

  function step() {
    if (state.running) return;
    if (state.contractError || (state.phase < 0 && contractIssue())) {
      renderContractError();
      return;
    }
    if (state.phase >= 4) {
      reset(false);
      updatePhase(0);
    } else {
      updatePhase(state.phase + 1);
    }
  }

  function reset(announce = true) {
    window.clearInterval(state.timer);
    state.running = false;
    state.phase = -1;
    state.result = null;
    state.contractError = false;
    state.filter = "all";
    $$(".filter").forEach((item) => item.classList.toggle("active", item.dataset.filter === "all"));
    buildSamples();
    renderPlate();
    updatePhase(-1);
    $("#run-button").disabled = false;
    ["baseline-score", "candidate-score", "delta-score", "ci-low", "ci-high"].forEach((id) => $(`#${id}`).textContent = "—");
    ["baseline-bar", "candidate-bar"].forEach((id) => $(`#${id}`).style.width = "0");
    const card = $("#verdict-card");
    card.classList.remove("blocked", "passed", "contract-error");
    $("#verdict").textContent = "NOT RUN";
    $("#verdict-reason").textContent = "Run the protocol to produce a verdict.";
    $(".proof-mark").textContent = "UNREAD";
    $("#chart-empty").hidden = false;
    const ctx = $("#score-chart").getContext("2d");
    ctx.clearRect(0, 0, $("#score-chart").width, $("#score-chart").height);
    $("#specimen-title").textContent = "Select a sample";
    $("#specimen-status").textContent = "UNREAD";
    $("#sample-slice").textContent = "—";
    $("#sample-score").textContent = "—";
    $("#sample-input").textContent = "Choose any well to open its paired evidence.";
    $("#sample-before").textContent = "—";
    $("#sample-after").textContent = "—";
    $("#sample-note").textContent = "Aggregate scores cannot explain a failure. The specimen can.";
    $("#recover-button").hidden = true;
    $("#copy-button").disabled = true;
    $("#export-button").disabled = true;
    if (announce) toast("Bench reset. No verdict is active.");
  }

  function evidence() {
    const result = state.result || calculateResult();
    return {
      assay: "A-0012",
      generated_from: "bundled deterministic fixture",
      baseline_run: $("#baseline").value,
      candidate_run: $("#candidate").value,
      source_runs: {
        baseline: source.baseline_run,
        candidate: source.candidate_run
      },
      suite: $("#suite").value,
      dataset_hash: $("#dataset-pin").textContent,
      scorer: scorerLabels[$("#scorer").value],
      scorer_hash: $("#scorer-pin").textContent,
      comparison: result,
      scope: source.scope
    };
  }

  function reviewNote() {
    const bundle = evidence();
    const result = bundle.comparison;
    return [
      `ASSAY ${bundle.assay} · ${result.verdict}`,
      `${bundle.baseline_run} ${fmt(result.baseline)} → ${bundle.candidate_run} ${fmt(result.candidate)} (${fmt(result.delta, true)})`,
      `95% paired CI [${fmt(result.ciLow, true)}, ${fmt(result.ciHigh, true)}] · tolerance ${result.tolerance.toFixed(2)}`,
      `${result.regressions.length} regressions: ${result.regressions.join(", ") || "none"}`,
      `dataset ${bundle.dataset_hash}`,
      `scorer ${bundle.scorer_hash}`,
      `Scope: ${bundle.scope}`
    ].join("\n");
  }

  function toast(message) {
    $("#toast").textContent = message;
    window.setTimeout(() => {
      if ($("#toast").textContent === message) $("#toast").textContent = "";
    }, 2800);
  }

  async function copyEvidence() {
    if (state.contractError || state.phase < 4) {
      toast("No evidence package exists until a compatible gate completes.");
      return;
    }
    const note = reviewNote();
    try {
      await navigator.clipboard.writeText(note);
      toast("Review note copied with hashes and sample IDs.");
    } catch (_error) {
      const field = document.createElement("textarea");
      field.value = note;
      document.body.appendChild(field);
      field.select();
      document.execCommand("copy");
      field.remove();
      toast("Review note copied with hashes and sample IDs.");
    }
  }

  function exportEvidence() {
    if (state.contractError || state.phase < 4) {
      toast("No evidence package exists until a compatible gate completes.");
      return;
    }
    const blob = new Blob([`${JSON.stringify(evidence(), null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `assay-${Date.now()}-evidence.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    toast("Evidence bundle exported.");
  }

  $("#run-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runFull();
  });
  $("#step-button").addEventListener("click", step);
  $("#reset-button").addEventListener("click", () => reset(true));
  $("#recover-button").addEventListener("click", () => {
    $("#candidate").value = "prompt-v2";
    renderPins();
    reset(false);
    toast("Compatible scorer pins restored. Run the assay to issue a verdict.");
    $("#candidate").focus();
  });
  $("#copy-button").addEventListener("click", copyEvidence);
  $("#export-button").addEventListener("click", exportEvidence);
  $("#tolerance").addEventListener("input", () => {
    $("#tolerance-value").textContent = Number($("#tolerance").value).toFixed(2);
    if (state.phase >= 4) updateVerdict();
  });
  ["suite", "candidate", "baseline", "scorer"].forEach((id) => {
    $(`#${id}`).addEventListener("change", () => {
      const recovering = state.contractError;
      if (id === "suite") {
        $("#scorer").value = $("#suite").value === "world-core" ? "grounding" : "accuracy";
      }
      if (id === "scorer") {
        $("#suite").value = $("#scorer").value === "accuracy" ? "prod-agents" : "world-core";
      }
      renderPins();
      reset(false);
      if (recovering && !contractIssue()) {
        toast("Compatible pins selected. Run the assay to issue a verdict.");
      }
    });
  });
  $$(".filter").forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      $$(".filter").forEach((item) => item.classList.toggle("active", item === button));
      renderPlate();
    });
  });
  window.addEventListener("resize", () => {
    if (state.phase >= 3) drawChart();
  });
  window.addEventListener("keydown", (event) => {
    if (event.key.toLowerCase() === "r" && !/input|select|textarea/i.test(document.activeElement.tagName)) {
      runFull();
    }
  });

  renderPins();
  reset(false);
})();
