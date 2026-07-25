# ASSAY local service operations

The local service is the installed production path for already-scored model or
world-model runs. It is keyless because it does not call a provider: callers
produce predictions and scores, then ASSAY verifies contracts, persists runs,
compares them, and retains evidence.

The GitHub Pages app is separate. It is a static replay and cannot write to this
service.

## Start and verify

```bash
python -m pip install .
assay serve --db .assay/runs.sqlite --host 127.0.0.1 --port 8765
```

| Probe | Meaning |
| --- | --- |
| `GET /healthz` | The HTTP process is alive. |
| `GET /readyz` | SQLite accepts a query. Use this for readiness and container health. |
| `GET /api/v1/openapi.json` | Machine-readable route inventory. |
| `GET /app/` | Same-origin operator UI backed by the API. |

Seed the deterministic pair only when wanted:

```bash
assay serve --seed-demo
# or, separately
assay seed-demo --db .assay/runs.sqlite
```

## Configuration

CLI flags override these environment variables.

| Variable | Default | Notes |
| --- | --- | --- |
| `ASSAY_DB` | `.assay/runs.sqlite` | Parent directories are created. WAL and a five-second busy timeout are enabled for file databases. |
| `ASSAY_HOST` | `127.0.0.1` | Loopback is the safe default. |
| `ASSAY_PORT` | `8765` | Use `0` in tests to request an ephemeral port. |
| `ASSAY_MAX_BODY_BYTES` | `2097152` | Maximum JSON request body. |
| `ASSAY_CORS_ORIGIN` | unset | Exact `Access-Control-Allow-Origin` value. Same-origin UI needs no CORS. |

The service has no authentication, authorization, tenant isolation, rate
limiting, or TLS. Put it behind a trusted authenticated reverse proxy before
binding beyond loopback. A warning is printed for non-loopback binds.

## Run envelope

`POST /api/v1/runs` and `assay ingest` accept:

```json
{
  "run": {
    "run_id": "candidate-2026-07-25",
    "dataset_hash": "sha256:<64 lowercase hex characters>",
    "scorer_hash": "sha256:<64 lowercase hex characters>",
    "model_id": "model-v2",
    "metadata": {"commit": "abc123"},
    "samples": [
      {
        "sample_id": "case-001",
        "context": {"request": "select a tool"},
        "action": "choose_tool",
        "reference": "search",
        "prediction": "search",
        "scores": {"accuracy": 1.0}
      }
    ]
  },
  "scorer": {
    "name": "exact_tool_selection",
    "version": "1.0.0",
    "config": {},
    "scorer_hash": "sha256:<hash of name, version, and config>"
  }
}
```

Generate hashes with the library instead of writing them by hand:

```python
from assay import Dataset, ScorerSpec

dataset = Dataset.create([
    {
        "sample_id": "case-001",
        "context": {"request": "select a tool"},
        "action": "choose_tool",
        "reference": "search",
    }
])
scorer = ScorerSpec.create("exact_tool_selection", "1.0.0")
print(dataset.content_hash)
print(scorer.to_dict())
```

The dataset hash covers ordered sample ID/context/action/reference records.
Prediction and score changes therefore do not create a new dataset, while label,
context, or action changes do. Scorer name/version/config must reproduce its
declared hash. The run must pin that exact scorer hash.

## Compare and gate

```bash
assay compare --db .assay/runs.sqlite \
  --baseline main-abc123 --candidate pr-482-def456 \
  --metric accuracy --tolerance 0.01 \
  --output evidence.json
```

Equivalent API request:

```http
POST /api/v1/comparisons
Content-Type: application/json

{
  "baseline_run_id": "main-abc123",
  "candidate_run_id": "pr-482-def456",
  "metric": "accuracy",
  "alpha": 0.05,
  "metric_count": 1,
  "tolerance": 0.01
}
```

Successful inference returns HTTP 200 and a persisted
`assay.comparison-evidence.v1` record containing parameters, hashes, summary,
verdict, and paired sample evidence.

- `PASSED`: `assay gate` exits 0.
- `BLOCKED`: evidence is stored and `assay gate` exits 1.
- `UNDETERMINED`: evidence is stored with unavailable numeric fields encoded as
  JSON `null`; `assay gate` exits 2.
- Dataset/scorer/sample contract errors: HTTP 409 or CLI exit 2. No comparison
  evidence is created.
- Invalid input or missing metrics: HTTP 422 or CLI exit 2.

Comparison IDs are deterministic for a baseline, candidate, metric, alpha,
metric count, and tolerance. Identical retries return the original evidence.

## Persistence and recovery

SQLite is the system of record for:

- content-addressed dataset definitions;
- versioned scorer contracts;
- immutable runs;
- durable comparison evidence.

Back up a stopped instance by copying the database and any `-wal`/`-shm` files,
or use SQLite’s online backup tooling. Restore by starting ASSAY against the
restored database. The schema version is recorded in `PRAGMA user_version`.

The current schema is single-node and migration framework-free. Before a future
schema upgrade, take a backup and follow that release’s migration notes.

## Container

```bash
docker build -t assay-local .
docker run --rm -p 127.0.0.1:8080:8080 \
  -v assay-data:/data assay-local
```

The image:

- installs the wheel-compatible package;
- runs as UID 10001;
- persists `/data`;
- exposes port 8080;
- seeds the deterministic pair idempotently;
- uses `/readyz` for its health check.

## Failure handling

All API errors use:

```json
{
  "error": {
    "code": "scorer_mismatch",
    "message": "cross-scorer-version diff is forbidden",
    "details": {},
    "retryable": false
  },
  "request_id": "..."
}
```

Every response includes `X-Request-ID`. Client-provided request IDs are echoed
for correlation. Request bodies use strict JSON; non-finite constants are
rejected. Static responses include a restrictive content-security policy and
basic anti-sniffing/framing headers.
