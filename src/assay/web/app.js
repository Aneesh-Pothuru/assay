(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const state = { runs: [], evidence: null, filter: "all" };

  function text(value) {
    return value === null || value === undefined ? "—" : String(value);
  }

  function number(value, signed = false) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    const numeric = Number(value);
    return `${signed && numeric >= 0 ? "+" : ""}${numeric.toFixed(3)}`;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: options.body ? { "Content-Type": "application/json" } : {},
      ...options
    });
    const payload = await response.json();
    if (!response.ok) {
      const error = new Error(payload.error?.message || `HTTP ${response.status}`);
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function setService(status, copy) {
    $(".service-state").classList.remove("ready", "error");
    $(".service-state").classList.add(status);
    $("#service-state").textContent = copy;
  }

  function runById(id) {
    return state.runs.find((run) => run.run_id === id);
  }

  function option(run) {
    const item = document.createElement("option");
    item.value = run.run_id;
    item.textContent = `${run.run_id} · ${run.model_id} · n=${run.sample_count}`;
    return item;
  }

  function renderPins() {
    const baseline = runById($("#baseline").value);
    const candidate = runById($("#candidate").value);
    const values = [
      ["baseline-dataset", baseline?.dataset_hash],
      ["candidate-dataset", candidate?.dataset_hash],
      ["baseline-scorer", baseline?.scorer_hash],
      ["candidate-scorer", candidate?.scorer_hash]
    ];
    values.forEach(([id, value]) => {
      $(`#${id}`).textContent = text(value);
      $(`#${id}`).classList.remove("mismatch");
    });
    if (baseline && candidate) {
      if (baseline.dataset_hash !== candidate.dataset_hash) {
        $("#baseline-dataset").classList.add("mismatch");
        $("#candidate-dataset").classList.add("mismatch");
      }
      if (baseline.scorer_hash !== candidate.scorer_hash) {
        $("#baseline-scorer").classList.add("mismatch");
        $("#candidate-scorer").classList.add("mismatch");
      }
    }
  }

  async function loadRuns() {
    setService("", "Checking readiness");
    const readiness = await api("/readyz");
    if (readiness.status !== "ready") throw new Error("service is not ready");
    const payload = await api("/api/v1/runs");
    state.runs = payload.runs;
    const previousBaseline = $("#baseline").value;
    const previousCandidate = $("#candidate").value;
    $("#baseline").innerHTML = "";
    $("#candidate").innerHTML = "";
    state.runs.forEach((run) => {
      $("#baseline").appendChild(option(run));
      $("#candidate").appendChild(option(run));
    });
    if (state.runs.length) {
      $("#baseline").value = state.runs.some((run) => run.run_id === previousBaseline)
        ? previousBaseline : state.runs[0].run_id;
      $("#candidate").value = state.runs.some((run) => run.run_id === previousCandidate)
        ? previousCandidate : (state.runs[1] || state.runs[0]).run_id;
    }
    $("#run-count").textContent = `${state.runs.length} runs`;
    $("#compare-button").disabled = state.runs.length < 2;
    renderPins();
    setService("ready", "Service ready");
  }

  function clearEvidence() {
    state.evidence = null;
    $("#download-button").disabled = true;
    $("#evidence-id").textContent = "No comparison evidence stored";
    $("#sample-plate").innerHTML = "";
    ["all", "regressed", "improved", "held"].forEach((status) => {
      $(`#${status}-count`).textContent = "0";
    });
    $("#sample-title").textContent = "No evidence loaded";
    ["sample-status", "sample-score", "sample-context", "sample-reference", "sample-baseline", "sample-candidate"]
      .forEach((id) => { $(`#${id}`).textContent = "—"; });
  }

  function showError(error) {
    clearEvidence();
    const payload = error.payload?.error;
    $("#error-card").hidden = false;
    $("#error-code").textContent = (payload?.code || "request_failed").replaceAll("_", " ").toUpperCase();
    $("#error-message").textContent = payload?.message || error.message;
    const card = $("#verdict-card");
    card.classList.remove("blocked", "passed", "undetermined");
    card.classList.add("undetermined");
    $("#verdict").textContent = "MERGE WITHHELD";
    $("#verdict-reason").textContent = "The comparison contract failed before a verdict could be issued.";
    ["baseline-score", "candidate-score", "delta-score", "ci-score"]
      .forEach((id) => { $(`#${id}`).textContent = "—"; });
  }

  function selectSample(index) {
    const sample = state.evidence?.samples[index];
    if (!sample) return;
    $$(".well").forEach((well) => {
      well.classList.toggle("selected", Number(well.dataset.index) === index);
    });
    $("#sample-title").textContent = sample.sample_id;
    $("#sample-status").textContent = sample.status.toUpperCase();
    $("#sample-score").textContent = `${number(sample.baseline_score)} → ${number(sample.candidate_score)}`;
    $("#sample-context").textContent = JSON.stringify(sample.context);
    $("#sample-reference").textContent = JSON.stringify(sample.reference);
    $("#sample-baseline").textContent = JSON.stringify(sample.baseline_prediction);
    $("#sample-candidate").textContent = JSON.stringify(sample.candidate_prediction);
  }

  function renderPlate() {
    const plate = $("#sample-plate");
    plate.innerHTML = "";
    const samples = state.evidence?.samples || [];
    ["all", "regressed", "improved", "held"].forEach((status) => {
      const count = status === "all" ? samples.length : samples.filter((sample) => sample.status === status).length;
      $(`#${status}-count`).textContent = String(count);
    });
    samples.forEach((sample, index) => {
      const well = document.createElement("button");
      well.type = "button";
      well.className = `well ${sample.status}`;
      well.dataset.index = String(index);
      well.dataset.status = sample.status;
      well.hidden = state.filter !== "all" && state.filter !== sample.status;
      well.setAttribute("aria-label", `${sample.sample_id}: ${sample.status}`);
      well.addEventListener("click", () => selectSample(index));
      plate.appendChild(well);
    });
    if (samples.length) selectSample(0);
  }

  function renderEvidence(evidence) {
    state.evidence = evidence;
    $("#error-card").hidden = true;
    const comparison = evidence.comparison;
    const card = $("#verdict-card");
    card.classList.remove("blocked", "passed", "undetermined");
    card.classList.add(comparison.verdict.toLowerCase());
    $("#verdict").textContent = comparison.verdict === "BLOCKED"
      ? "MERGE BLOCKED"
      : comparison.verdict === "PASSED"
        ? "MERGE PERMITTED"
        : "NO VERDICT";
    $("#verdict-reason").textContent = comparison.reason;
    $("#baseline-score").textContent = number(comparison.baseline);
    $("#candidate-score").textContent = number(comparison.candidate);
    $("#delta-score").textContent = number(comparison.delta, true);
    $("#ci-score").textContent = `[${number(comparison.ci_low, true)}, ${number(comparison.ci_high, true)}]`;
    $("#download-button").disabled = false;
    $("#evidence-id").textContent = `${evidence.comparison_id} · persisted`;
    renderPlate();
  }

  async function compare(event) {
    event.preventDefault();
    $("#compare-button").disabled = true;
    $("#error-card").hidden = true;
    clearEvidence();
    try {
      const evidence = await api("/api/v1/comparisons", {
        method: "POST",
        body: JSON.stringify({
          baseline_run_id: $("#baseline").value,
          candidate_run_id: $("#candidate").value,
          metric: $("#metric").value,
          tolerance: Number($("#tolerance").value),
          alpha: 0.05,
          metric_count: 1
        })
      });
      renderEvidence(evidence);
    } catch (error) {
      showError(error);
    } finally {
      $("#compare-button").disabled = state.runs.length < 2;
    }
  }

  function downloadEvidence() {
    if (!state.evidence) return;
    const blob = new Blob([`${JSON.stringify(state.evidence, null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${state.evidence.comparison_id}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
  }

  $("#compare-form").addEventListener("submit", compare);
  $("#refresh-button").addEventListener("click", () => loadRuns().catch(showError));
  $("#download-button").addEventListener("click", downloadEvidence);
  ["baseline", "candidate"].forEach((id) => {
    $(`#${id}`).addEventListener("change", renderPins);
  });
  $$(".filter").forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      $$(".filter").forEach((item) => item.classList.toggle("active", item === button));
      renderPlate();
    });
  });

  clearEvidence();
  loadRuns().catch((error) => {
    setService("error", "Service unavailable");
    showError(error);
  });
})();
