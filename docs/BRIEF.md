# 04 · ASSAY

**One evaluation platform for language models and world models — because
both are predictors you score against a held-out future, and only one of
them has decent tooling.**

`assay` · Python · SQLite/Parquet · CI-native · Kaggle/Colab for GPU

---

## Objective

LLM evaluation has a mature product category. World-model evaluation has
a pile of mutually incompatible academic benchmarks and no CI story at
all. ASSAY unifies them under one abstraction — **a model proposes a
continuation, a scorer compares it to ground truth or a task outcome,
and a gate decides whether that's a regression** — and makes the result
something you can block a merge on.

The unifying insight: an LLM eval sample and a world-model rollout are
the same object, `(context, action/prompt) → predicted future`, scored
against a reference. The difference is the modality and the scorer, not
the infrastructure.

---

## Why now

**LLM eval is a settled product category converging on CI gates** —
Braintrust, LangSmith, Langfuse, Inspect
([comparison](https://www.braintrust.dev/articles/langsmith-alternatives-2026),
[frameworks](https://www.callmissed.com/en/blog/agent-evaluation-frameworks-compared-braintrust-vs-inspect-vs-langfuse-vs-diy-20)) —
with a known weakness: you define the eval surface upfront and unknown
failures stay unknown.

**World-model eval is fragmented and pre-product:**

- Genie, YUME, HY-World, Matrix-Game — each evaluated on its own private
  benchmark; fair comparison impossible
  ([WorldMark](https://arxiv.org/html/2604.21686v1)).
- The existing benchmarks are partial and don't compose:
  [WorldModelBench](https://worldmodelbench-team.github.io/) (instruction
  following, physics adherence, 350 pairs / 67k annotations),
  [WorldBench](https://world-bench.github.io/) (physics diagnostics),
  [MBench](https://arxiv.org/html/2606.00793v1) (memory consistency),
  WorldArena (perception + functional utility).
- An active position argues world models should be evaluated by
  **decision-making utility, not perceptual fidelity**
  ([position](https://arxiv.org/pdf/2606.15032)) — the thing everyone
  measures is the wrong thing.
- Stakes just rose: generative world models are now **closed-loop policy
  evaluators** for AVs ([NVIDIA OmniDreams](https://arxiv.org/abs/2606.03159)).
  When the simulator is a neural net, the validity of your evaluation
  depends on a model you also have to evaluate. Nobody has tooling for
  that recursion.

**The blog post this proves:** "What a Good Eval Harness Refuses to Do" —
a useful harness says *no*: no unversioned datasets, no cross-scorer
diffs, no vibes.

---

## Non-goals

- Not a new benchmark — ASSAY *runs* existing ones under one interface.
- Not observability — traces come from loopkit; ASSAY scores and gates.
- Not a judge model — it hosts judges and, more importantly, **evaluates
  the judges**. (Auditing whole benchmarks for validity is SIEVE's job;
  the boundary: ASSAY runs evals and gates regressions, SIEVE audits
  whether the evals deserve trust.)

---

## Personas

| Persona | Cares about |
|---|---|
| **ML engineer** shipping a change | "Did this regress anything? Tell me in CI, before merge." |
| **World-model researcher** | "My dynamics model vs three others, same scenes, one table." |
| **Robotics/AV eval owner** | "If I evaluate policies inside a learned simulator, how far do I trust the verdict?" |

---

## User journeys

### Journey 0 — the demo (no API key, <10 minutes)

```bash
pipx install assay && assay demo
```

Replays two bundled eval runs — the same 100-sample task set scored
against two model versions — and renders the comparison report: aggregate
deltas with CIs, the 12 specific samples that regressed, and a gate
verdict (`BLOCKED`, exit 1). Then `assay demo --gate-in-ci` prints a
ready-to-paste GitHub Actions workflow. Keyless, instant, and it shows
the whole product: *per-sample regressions you can block a merge on.*

Live mode: `assay run --suite demo --model gemini-2.5-flash` re-scores
the suite on a free key (100 samples ≈ 100 requests — well within free
quota).

### J1 — A merge is blocked by a regression

Ana changes a prompt template. CI runs `assay run --suite prod-agents`
against a version-pinned dataset:

```
REGRESSION  tool_selection_accuracy  0.91 → 0.86  (CI excludes 0, n=800)
HELD        latency_p95              1.9s → 2.0s  (within tolerance)
NEW-FAILURE 12 samples fail that passed on main   → assay diff --failures
BLOCKED     gate: prod-agents
```

Twelve concrete samples, not an aggregate mood.

### J2 — Four world models, one scoreboard

Ravi has four action-conditioned dynamics checkpoints. `assay run
--suite worldmodel-core --models ckpt-{a,b,c,d}` executes them against a
**fixed scene/trajectory set**:

| | open-loop drift @H=16 | action grounding | memory | task utility |
|---|---|---|---|---|
| ckpt-a | 0.31 | **0.88** | 0.62 | 0.44 |
| ckpt-b | **0.22** | 0.71 | 0.59 | 0.41 |
| ckpt-c | 0.29 | 0.74 | **0.77** | **0.53** |

The columns are exactly the failure modes worth separating: compounding
error over horizon; whether perturbing `aₜ` moves the right latents and
nothing else; whether world state persists through occlusion; whether a
policy trained inside the model works outside it. Fixed scenes are the
point — the comparison WorldMark says is currently impossible.

### J3 — Evaluating the evaluator

Ravi's team wants ckpt-c as a closed-loop policy evaluator. ASSAY's
**simulator validity suite** takes policies with known real rankings,
ranks them inside the world model, and reports rank correlation vs.
horizon:

```
rank-correlation   ρ = 0.81 @ H≤8 · ρ = 0.34 @ H≥24
safe-horizon       8 steps (ρ ≥ 0.75)
VERDICT            usable as policy evaluator up to 8-step horizons; not beyond
```

`safe_horizon` — the horizon at which your neural simulator stops being a
valid judge — is the most useful artifact in this project. Nobody
publishes it.

### J4 — The judge gets judged

A suite uses LLM-as-judge scoring. ASSAY tracks judge-vs-human agreement
on a held-out labeled slice per release and flags drift:

```
WARN judge/drift  agreement 0.88 → 0.79 since judge model update
     scores across this boundary are not comparable
```

### End-to-end journey (the product loop)

Version a dataset → register scorers → baseline run → wire the gate into
CI → every model/prompt/checkpoint change runs the suite → regressions
block with per-sample evidence → judges monitored for drift → world-model
checkpoints get the same treatment on fixed scenes → before anyone uses a
world model *as* an evaluator, its `safe_horizon` is on record.

---

## PRD

### P0

| ID | Requirement |
|---|---|
| P0-1 | **Unified sample abstraction** — `(context, action, reference) → prediction → scores`; same object for an LLM sample, a rollout, a sim scenario. |
| P0-2 | **Versioned datasets** — content-addressed; runs pin the hash; **refuses to run unversioned data**. |
| P0-3 | **Scorer registry** — versioned, content-addressed scorers; cross-scorer-version diffs are a hard error. |
| P0-4 | **Comparison engine** — CIs, multiple-comparison correction, per-sample regressions. |
| P0-5 | **CI gate** — `assay gate` exit codes + structured report; GitHub Actions recipe in-repo. |
| P0-6 | **World-model scorer family** — `wm/drift` (error-vs-horizon curve), `wm/grounding` (action-perturbation selectivity), `wm/memory` (consistency through occlusion), `wm/utility` (policy trained in-model, run out-of-model) — shipped **CPU-scale first** (see design). |
| P0-7 | **Record/replay** — bundled runs render keylessly (Journey 0). |
| P0-8 | **loopkit conformance** — samples are `Run`s; ASSAY owns `score()`/`judge()` and the verdict vocabulary. |

### P1

| ID | Requirement |
|---|---|
| P1-1 | **Simulator validity suite** — rank-correlation-vs-horizon, `safe_horizon` verdict. |
| P1-2 | **Judge monitoring** — human-agreement tracking, drift alarms, comparability boundaries. |
| P1-3 | **Benchmark adapters** — run WorldModelBench/WorldBench/MBench-class suites under the ASSAY interface via Kaggle/Colab notebook jobs. |
| P1-4 | **Unknown-failure clustering** — embed failing samples, surface clusters no metric covers (the incumbents' known gap). |
| P1-5 | **Cost/latency as first-class scores** — every suite reports quality *and* cost. |

### P2

- Adaptive sampling (spend eval budget where variance is highest).
- Eval-set health: saturation, leakage, suspected label errors (handed to SIEVE).
- Public fixed-scene world-model leaderboard.

### Success metrics

| Metric | Target |
|---|---|
| Demo: clone → replayed comparison + gate | < 10 min, $0, keyless |
| Seeded-regression detection | ≥ 95% at ≤ 5% false-positive |
| Gate in a real CI pipeline | working recipe, < 5 min overhead on the demo suite |
| World-model scorers validated on CPU-scale reference models | all four, reproducible via `make reproduce-wm` |
| Cross-model world-model table on fixed scenes | ≥ 2 public checkpoints via free GPU notebooks (≥ 4 by v1.0) |
| `safe_horizon` published for public world models | ≥ 1 at launch, ≥ 2 by v1.0, method documented |

### Launch-day definition

`assay demo` (keyless replay + gate), live LLM path on Gemini/Groq free
keys, CI recipe proven in this repo's own Actions, four `wm/*` scorers
running on the CPU-scale reference stack, first `safe_horizon` number
published with its notebook, LIMITS.md (which benchmark adapters exist,
GPU costs of the big suites, known provider nondeterminism).

### Risks

| Risk | Mitigation |
|---|---|
| Crowded LLM-eval market | Don't compete there; the wedge is world models + the unified abstraction. LLM eval is table stakes that comes along free |
| Unification is superficial | Prove it in v0.1: the world-model path must reuse the sample/scorer/diff machinery unchanged, or the abstraction gets fixed then |
| World-model suites are GPU-heavy | Two-tier design: CPU-scale reference stack in-repo; big public checkpoints via Kaggle (30 h/wk) / Colab / Lightning (80 h/mo) notebooks with results checked in |
| Metric zoo without meaning | Task utility is the headline metric (per the decision-centric position); perceptual metrics are diagnostics |

---

## System design

```
 datasets (hashed) ─┐            models / world models
                    ▼                      ▼
             ┌────────────┐        ┌──────────────┐
             │ SAMPLE     │───────▶│ RUNNER       │  batched, resumable,
             │ LOADER     │◀───────│ (LiteLLM or  │  request-budget aware
             └────────────┘  refs  │  torch)      │
                                   └──────┬───────┘
                                          │ predictions
                     ┌────────────────────┤
                     ▼                    ▼
           ┌──────────────────┐  ┌──────────────────┐
           │ SCORER REGISTRY  │  │ RUN STORE        │
           │ text/* judge/*   │  │ (SQLite+Parquet, │
           │ wm/drift·ground· │  │  loopkit Run)    │
           │ memory·utility   │  └──────────────────┘
           └────────┬─────────┘
                    ▼
           ┌──────────────────┐   ┌──────────────┐   ┌────────────────┐
           │ COMPARISON ENGINE│──▶│ GATE         │   │ VALIDITY SUITE │
           │ (CIs, per-sample)│   │ (exit codes) │   │ (safe_horizon) │
           └────────┬─────────┘   └──────────────┘   └────────────────┘
                    ▼
           ┌──────────────────┐   ┌──────────────┐
           │ REPORT / REPLAY  │   │ JUDGE MONITOR│
           └──────────────────┘   └──────────────┘
```

**Two-tier world-model strategy (the free-tier fix).** Tier 1, in-repo:
a **CPU-scale reference stack** — a small latent dynamics model on a
dm_control/gridworld-class environment, trainable in minutes — on which
all four `wm/*` scorers run end-to-end in CI. This proves the scorers
and the abstraction. Tier 2: adapters + Kaggle/Colab notebooks that run
the same scorers on real public checkpoints within free GPU hours;
result Parquet files get checked in and rendered by the same report
machinery. The published tables come from tier 2; the tests come from
tier 1.

**The four scorers** map to the field's named failure modes: compounding
error (curve, not scalar), action-grounding selectivity (the metric the
field most conspicuously lacks), memory through occlusion, and
in-model→out-of-model policy transfer — the only metric that answers the
question that matters.

**Scorer versioning is a hard invariant.** Refusing cross-version diffs
is most of what separates an eval platform from a spreadsheet.

### Interfaces

- **→ everyone** — owns `score()`/`judge()` + verdict vocabulary in
  loopkit (vendored by the other five from day one; live integration
  v0.3).
- **← TERRARIUM** — run bundles scored; suite trends gated.
- **← SIEVE** — SIEVE audits ASSAY's datasets and judges for validity;
  ASSAY flags suspects (saturation, weird distributions) and hands them
  to SIEVE.
- **← FLOTILLA** — kill predicates over ASSAY scores.
- **← BATON** — lesson-promotion gate uses ASSAY scoring.

### Milestones

| | Scope |
|---|---|
| **v0.1** | Sample abstraction, versioned datasets, scorer registry, comparison engine, gate, replay demo. Text path complete. **Journey 0 works.** |
| **v0.2** | Four `wm/*` scorers on the CPU reference stack; first Kaggle notebook adapter; judge monitoring. |
| **v0.3** | Simulator validity suite + first published `safe_horizon`. **Launch.** |
| **v1.0** | Unknown-failure clustering, ≥4-checkpoint world-model table, adapters for two more public benchmarks. |

### Stack & free tier

Python 3.12 · SQLite + Parquet (DuckDB for comparisons) · LiteLLM
(Gemini 1,500 req/day; Groq; Ollama) · PyTorch CPU for the reference
stack · Kaggle (30 GPU-h/wk) + Colab + Lightning (80 GPU-h/mo) for real
checkpoints · GitHub Actions for the gate recipe · reports on GitHub
Pages. Total required spend: **$0**.
