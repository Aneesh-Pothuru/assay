# ASSAY

ASSAY is a small, deterministic evaluation harness for language-model samples
and world-model rollouts. Both use one content-addressed sample and scorer
contract, one per-sample comparison engine, and one CI gate.

The build brief is copied to [`docs/BRIEF.md`](docs/BRIEF.md). This repository
implements the P0 contract with standard-library Python. It deliberately does
not claim public-checkpoint or provider measurements; see
[`LIMITS.md`](LIMITS.md).

## Journey 0

```bash
git clone https://github.com/Aneesh-Pothuru/assay
cd assay
make demo
```

The demo needs no API key or network. It compares two bundled 100-sample runs,
finds the twelve seeded regressions, computes a paired confidence interval,
writes [`docs/demo/index.html`](docs/demo/index.html), and observes the required
`BLOCKED` gate. The `assay demo` command itself exits `1`; `make demo` treats
that expected gate result as success.

![ASSAY per-sample regression report](docs/assets/demo.jpg)

After installation, the brief's command also works:

```bash
python -m pip install .
assay demo                 # expected exit code: 1
assay demo --gate-in-ci
```

## Commands

```bash
make test
make lint
make reproduce-seeded-regression
make reproduce-wm
```

`make reproduce-wm` executes four scorer contracts on a tiny deterministic
gridworld fixture: drift-over-horizon, action grounding, memory through
occlusion, and in-model to out-of-model utility. These are contract/reference
tests, not measurements on public checkpoints.

## Architecture

```text
versioned samples ──> Run records ──> versioned scorer
       │                                   │
       └──────── comparison + CI <─────────┘
                         │
                 structured gate
                         │
                  JSON + static HTML
```

Datasets and scorers are content-addressed. A run pins both hashes, unversioned
dataset payloads are rejected, and cross-scorer-version comparisons raise a
hard error. The vendored `loopkit` subset is in
`src/assay/schemas/loopkit.py`.
