# ASSAY

ASSAY is a deterministic evaluation harness for language-model samples and
world-model rollouts. Both use one content-addressed sample and scorer
contract, one per-sample comparison engine, and one CI gate.

The [product site](https://aneesh-pothuru.github.io/assay/) explains the thesis,
evidence, method, architecture, and honest limits. Its
[interactive evaluation bench](https://aneesh-pothuru.github.io/assay/demo/)
is an explicitly labeled static replay over embedded fixture data.

The build brief is copied to [`docs/BRIEF.md`](docs/BRIEF.md). This repository
implements the P0 contract and a keyless local HTTP service with standard-library
Python. Installed users can ingest real scored run records, persist them in
SQLite, invoke the actual comparison engine through CLI or API, and inspect the
durable evidence in a packaged operator UI. ASSAY does not execute model
providers; see [`LIMITS.md`](LIMITS.md).

## Choose the right surface

| Surface | Data | Engine | Persistence | Intended use |
| --- | --- | --- | --- | --- |
| GitHub Pages bench | Embedded deterministic fixtures and additional labeled UI profiles | Browser interaction model | None | Learn and inspect the workflow |
| `assay demo` | Bundled 100-sample runs | Python comparison engine | Generated JSON + HTML | Reproduce Journey 0 |
| `assay serve` / `assay compare` | User-ingested scored `Run` envelopes | Python comparison engine | SQLite runs, contracts, and evidence | Local operational evaluation |

## Journey 0 · reproducible fixture

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

![ASSAY interactive evaluation bench](docs/assets/demo.jpg)

After installation, the brief's command also works:

```bash
python -m pip install .
assay demo                 # expected exit code: 1
assay demo --gate-in-ci
```

## Journey 1 · real local service

```bash
python -m pip install .
assay serve --seed-demo --db .assay/runs.sqlite
```

Open <http://127.0.0.1:8765/app/>. The operator UI fetches persisted runs from
`/api/v1/runs`, posts the selected pair to `/api/v1/comparisons`, and renders
the returned durable evidence. Health and readiness are separate:

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/readyz
```

The same path works without a browser:

```bash
assay seed-demo --db .assay/runs.sqlite
assay compare --db .assay/runs.sqlite \
  --baseline demo-baseline --candidate demo-candidate \
  --output .assay/evidence.json

# CI semantics: 0 PASSED, 1 BLOCKED, 2 UNDETERMINED or contract error.
assay gate --db .assay/runs.sqlite \
  --baseline demo-baseline --candidate demo-candidate
```

`assay ingest envelope.json --db .assay/runs.sqlite` accepts a scored `Run`
plus its versioned scorer contract. Dataset content is reconstructed from each
sample’s ID/context/action/reference and must match `dataset_hash`; the scorer
spec must reproduce `scorer_hash`. Run IDs are immutable and identical retries
are idempotent. See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for the envelope,
API, configuration, backup, Docker, and security boundary.

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
              SQLite evidence + JSON + UI
```

Datasets and scorers are content-addressed. A run pins both hashes, unversioned
dataset payloads are rejected, and cross-scorer-version comparisons raise a
hard error. The vendored `loopkit` subset is in
`src/assay/schemas/loopkit.py`. The HTTP and CLI surfaces share
`EvaluationService`; neither reimplements comparison semantics.

## Container

```bash
docker build -t assay-local .
docker run --rm -p 127.0.0.1:8080:8080 \
  -v assay-data:/data assay-local
```

The image runs as a non-root user, persists `/data/assay.sqlite`, and has a
`/readyz` health check. The service has no authentication or TLS and binds to
loopback by default outside the container. Do not expose it directly to an
untrusted network.

## Product UX

- [`docs/USER_JOURNEYS.md`](docs/USER_JOURNEYS.md) maps success, failure, and
  undetermined paths for ML engineers, reviewers, eval authors, and
  governance/infrastructure operators.
- [`docs/COMPETITIVE_UI.md`](docs/COMPETITIVE_UI.md) documents the primary-source
  product research and the distinctive clinical assay-bench direction.
- The GitHub Pages demo uses deterministic embedded fixtures. Extra candidate,
  suite, scorer, and tolerance states demonstrate the workflow; they are not
  presented as external model measurements.
- The packaged local UI consumes stored evidence from the real API. Contract
  mismatches withhold the merge and do not create exportable comparison records.
