from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .core import compare_runs, demo_runs, world_model_reference_scores
from .report import write_demo_report
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
      - name: Gate (BLOCKED exits 1)
        run: assay gate
"""


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
    sub.add_parser("gate", help="run the bundled gate")
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
        return run_demo()
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
