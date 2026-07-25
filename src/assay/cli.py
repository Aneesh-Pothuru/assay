from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from .core import RunStore, compare_runs, demo_runs, world_model_reference_scores
from .report import write_demo_report
from .service import APIError, EvaluationService, create_server
from .schemas.loopkit import Verdict


ROOT = Path.cwd()
DEMO_DIR = (
    ROOT / "docs" / "demo" if (ROOT / "docs").is_dir() else ROOT / "assay-demo"
)

WORKFLOW = """name: ASSAY regression gate
on: [push, pull_request]
jobs:
  assay:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install .
      - name: Seed deterministic example runs
        run: assay seed-demo --db .assay/runs.sqlite
      - name: Gate persisted runs (BLOCKED exits 1)
        run: >-
          assay gate --db .assay/runs.sqlite
          --baseline demo-baseline --candidate demo-candidate
          --output .assay/evidence.json
"""


def _json_default(value: str) -> int:
    try:
        return int(os.environ.get(value, ""))
    except ValueError:
        return 0


def _read_json(path: str) -> dict:
    text = sys.stdin.read() if path == "-" else Path(path).read_text()
    payload = json.loads(
        text,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"invalid JSON constant {value}")
        ),
    )
    if not isinstance(payload, dict):
        raise ValueError("JSON document must be an object")
    return payload


def _write_json(payload: dict, target: str | None = None) -> None:
    document = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if target and target != "-":
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document)
        print(f"WROTE {path}")
    else:
        print(document, end="")


def _service(db_path: str) -> tuple[RunStore, EvaluationService]:
    store = RunStore(db_path)
    return store, EvaluationService(store)


def seed_demo(db_path: str) -> int:
    store, service = _service(db_path)
    try:
        receipts = service.seed_demo()
    finally:
        store.close()
    _write_json({"database": db_path, "runs": receipts})
    return 0


def ingest_run(db_path: str, source: str) -> int:
    store, service = _service(db_path)
    try:
        receipt = service.ingest_run(_read_json(source))
    finally:
        store.close()
    _write_json(receipt)
    return 0


def compare_persisted(
    db_path: str,
    baseline: str,
    candidate: str,
    *,
    metric: str,
    alpha: float,
    metric_count: int,
    tolerance: float,
    output: str | None,
    gate: bool,
) -> int:
    store, service = _service(db_path)
    try:
        evidence = service.compare(
            {
                "baseline_run_id": baseline,
                "candidate_run_id": candidate,
                "metric": metric,
                "alpha": alpha,
                "metric_count": metric_count,
                "tolerance": tolerance,
            }
        )
    finally:
        store.close()
    _write_json(evidence, output)
    if not gate:
        return 0
    verdict = evidence["comparison"]["verdict"]
    if verdict == Verdict.PASSED.value:
        return 0
    if verdict == Verdict.BLOCKED.value:
        return 1
    return 2


def serve(
    db_path: str,
    host: str,
    port: int,
    *,
    seed: bool,
    cors_origin: str | None,
    max_body_bytes: int,
) -> int:
    store, service = _service(db_path)
    try:
        if seed:
            service.seed_demo()
        server = create_server(
            service,
            host,
            port,
            cors_origin=cors_origin,
            max_body_bytes=max_body_bytes,
        )
        actual_port = server.server_address[1]
        print(f"ASSAY local service http://{host}:{actual_port}/app/")
        print(f"SQLite {Path(db_path).resolve()}")
        if host not in {"127.0.0.1", "localhost", "::1"}:
            print(
                "WARNING: ASSAY has no authentication or TLS; use a trusted network boundary.",
                file=sys.stderr,
            )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("ASSAY service stopped")
        finally:
            server.server_close()
    finally:
        store.close()
    return 0


def run_demo() -> int:
    baseline, candidate = demo_runs()
    comparison = compare_runs(baseline, candidate)
    write_demo_report(DEMO_DIR / "index.html", baseline, candidate, comparison)
    print(
        f"{comparison.verdict.value} accuracy "
        f"{comparison.baseline:.2f} -> {comparison.candidate:.2f} "
        f"(delta {comparison.delta:+.2f}, "
        f"95% CI [{comparison.ci_low:+.3f}, {comparison.ci_high:+.3f}])"
    )
    print(f"NEW-FAILURE {len(comparison.regressions)} samples: "
          + ", ".join(comparison.regressions))
    print(f"REPORT {(DEMO_DIR / 'index.html').relative_to(ROOT)}")
    return 1 if comparison.verdict is Verdict.BLOCKED else 0


def reproduce_seeded() -> int:
    baseline, candidate = demo_runs()
    result = compare_runs(baseline, candidate)
    payload = {
        "fixture": "bundled-seeded-regression-v1",
        "seeded": 12,
        "detected": len(result.regressions),
        "false_positives": len(result.improvements),
        "detection_rate": len(result.regressions) / 12,
        "false_positive_rate": 0.0,
        "scope": "deterministic regression fixture; not an external benchmark",
    }
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    target = DEMO_DIR / "seeded-regression-results.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"WROTE {target.relative_to(ROOT)}")
    return 0


def reproduce_wm() -> int:
    payload = world_model_reference_scores()
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    target = DEMO_DIR / "wm-results.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"WROTE {target.relative_to(ROOT)}")
    return 0


def check() -> int:
    baseline, candidate = demo_runs()
    result = compare_runs(baseline, candidate)
    assert len(result.regressions) == 12
    assert result.verdict is Verdict.BLOCKED
    assert baseline.dataset_hash.startswith("sha256:")
    assert baseline.scorer_hash.startswith("sha256:")
    print("ASSAY self-check passed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="assay")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the bundled keyless replay")
    demo.add_argument(
        "--gate-in-ci", action="store_true", help="print a GitHub Actions recipe"
    )
    gate = sub.add_parser("gate", help="gate persisted runs, or the fixture with no IDs")
    gate.add_argument("--db", default=os.environ.get("ASSAY_DB", ".assay/runs.sqlite"))
    gate.add_argument("--baseline")
    gate.add_argument("--candidate")
    gate.add_argument("--metric", default="accuracy")
    gate.add_argument("--alpha", type=float, default=0.05)
    gate.add_argument("--metric-count", type=int, default=1)
    gate.add_argument("--tolerance", type=float, default=0.0)
    gate.add_argument("--output")
    compare = sub.add_parser("compare", help="compare two persisted runs")
    compare.add_argument("--db", default=os.environ.get("ASSAY_DB", ".assay/runs.sqlite"))
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--metric", default="accuracy")
    compare.add_argument("--alpha", type=float, default=0.05)
    compare.add_argument("--metric-count", type=int, default=1)
    compare.add_argument("--tolerance", type=float, default=0.0)
    compare.add_argument("--output")
    seed = sub.add_parser("seed-demo", help="persist the two deterministic demo runs")
    seed.add_argument("--db", default=os.environ.get("ASSAY_DB", ".assay/runs.sqlite"))
    ingest = sub.add_parser("ingest", help="ingest a run+scorer JSON envelope")
    ingest.add_argument("source", help="JSON file, or - for stdin")
    ingest.add_argument("--db", default=os.environ.get("ASSAY_DB", ".assay/runs.sqlite"))
    runs = sub.add_parser("runs", help="list persisted runs")
    runs.add_argument("--db", default=os.environ.get("ASSAY_DB", ".assay/runs.sqlite"))
    evidence = sub.add_parser("evidence", help="read persisted comparison evidence")
    evidence.add_argument("comparison_id")
    evidence.add_argument("--db", default=os.environ.get("ASSAY_DB", ".assay/runs.sqlite"))
    service = sub.add_parser("serve", help="start the keyless local HTTP service")
    service.add_argument("--db", default=os.environ.get("ASSAY_DB", ".assay/runs.sqlite"))
    service.add_argument("--host", default=os.environ.get("ASSAY_HOST", "127.0.0.1"))
    service.add_argument(
        "--port",
        type=int,
        default=_json_default("ASSAY_PORT") or 8765,
    )
    service.add_argument("--seed-demo", action="store_true")
    service.add_argument("--cors-origin", default=os.environ.get("ASSAY_CORS_ORIGIN"))
    service.add_argument(
        "--max-body-bytes",
        type=int,
        default=_json_default("ASSAY_MAX_BODY_BYTES") or 2 * 1024 * 1024,
    )
    sub.add_parser("reproduce-wm")
    sub.add_parser("reproduce-seeded-regression")
    sub.add_parser("check")
    run = sub.add_parser("run", help="provider runner status")
    run.add_argument("--suite", required=True)
    run.add_argument("--model", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        if args.gate_in_ci:
            print(WORKFLOW, end="")
            return 0
        return run_demo()
    if args.command == "gate":
        if bool(args.baseline) != bool(args.candidate):
            build_parser().error("--baseline and --candidate must be supplied together")
        if args.baseline:
            try:
                return compare_persisted(
                    args.db,
                    args.baseline,
                    args.candidate,
                    metric=args.metric,
                    alpha=args.alpha,
                    metric_count=args.metric_count,
                    tolerance=args.tolerance,
                    output=args.output,
                    gate=True,
                )
            except APIError as error:
                print(f"ASSAY {error.code}: {error.message}", file=sys.stderr)
                return 2
        return run_demo()
    if args.command == "compare":
        try:
            return compare_persisted(
                args.db,
                args.baseline,
                args.candidate,
                metric=args.metric,
                alpha=args.alpha,
                metric_count=args.metric_count,
                tolerance=args.tolerance,
                output=args.output,
                gate=False,
            )
        except APIError as error:
            print(f"ASSAY {error.code}: {error.message}", file=sys.stderr)
            return 2
    if args.command == "seed-demo":
        try:
            return seed_demo(args.db)
        except APIError as error:
            print(f"ASSAY {error.code}: {error.message}", file=sys.stderr)
            return 2
    if args.command == "ingest":
        try:
            return ingest_run(args.db, args.source)
        except (APIError, OSError, ValueError, json.JSONDecodeError) as error:
            message = error.message if isinstance(error, APIError) else str(error)
            print(f"ASSAY ingest failed: {message}", file=sys.stderr)
            return 2
    if args.command == "runs":
        with RunStore(args.db) as store:
            _write_json({"runs": store.list_runs()})
        return 0
    if args.command == "evidence":
        try:
            with RunStore(args.db) as store:
                payload = store.get_comparison(args.comparison_id)
        except KeyError:
            print(f"ASSAY comparison not found: {args.comparison_id}", file=sys.stderr)
            return 2
        _write_json(payload)
        return 0
    if args.command == "serve":
        return serve(
            args.db,
            args.host,
            args.port,
            seed=args.seed_demo,
            cors_origin=args.cors_origin,
            max_body_bytes=args.max_body_bytes,
        )
    if args.command == "reproduce-wm":
        return reproduce_wm()
    if args.command == "reproduce-seeded-regression":
        return reproduce_seeded()
    if args.command == "check":
        return check()
    if args.command == "run":
        print(
            "Live provider runners are not included in this dependency-free MVP. "
            "See LIMITS.md."
        )
        return 2
    raise AssertionError(args.command)
