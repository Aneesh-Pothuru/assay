import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from assay.core import (
    Dataset,
    RunStore,
    ScorerSpec,
    compare_runs,
    demo_runs,
    world_model_reference_scores,
)
from assay.report import write_demo_report
from assay.schemas.loopkit import Run, Verdict


class VersioningTests(unittest.TestCase):
    def test_dataset_requires_hash(self):
        with self.assertRaisesRegex(ValueError, "unversioned"):
            Dataset.from_payload({"samples": []})

    def test_dataset_rejects_wrong_hash(self):
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            Dataset.from_payload({"dataset_hash": "sha256:nope", "samples": []})

    def test_scorer_requires_version(self):
        with self.assertRaisesRegex(ValueError, "version"):
            ScorerSpec.create("accuracy", "")

    def test_cross_scorer_diff_is_hard_error(self):
        before, after = demo_runs()
        mismatched = Run(
            run_id=after.run_id,
            dataset_hash=after.dataset_hash,
            scorer_hash="sha256:different",
            model_id=after.model_id,
            samples=after.samples,
        )
        with self.assertRaisesRegex(ValueError, "cross-scorer-version"):
            compare_runs(before, mismatched)

    def test_sqlite_store_round_trips_version_pins(self):
        before, _ = demo_runs()
        store = RunStore()
        try:
            store.save(before)
            payload = store.get_payload(before.run_id)
        finally:
            store.close()
        self.assertEqual(payload["dataset_hash"], before.dataset_hash)
        self.assertEqual(payload["scorer_hash"], before.scorer_hash)


class ComparisonTests(unittest.TestCase):
    def test_demo_detects_exact_seeded_regressions_and_blocks(self):
        before, after = demo_runs()
        result = compare_runs(before, after)
        self.assertEqual(result.verdict, Verdict.BLOCKED)
        self.assertEqual(len(result.regressions), 12)
        self.assertEqual(result.regressions[0], "sample-000")
        self.assertEqual(result.regressions[-1], "sample-011")
        self.assertAlmostEqual(result.baseline, 1.0)
        self.assertAlmostEqual(result.candidate, 0.88)
        self.assertLess(result.ci_high, 0)

    def test_empty_run_abstains(self):
        scorer = ScorerSpec.create("accuracy", "1")
        dataset = Dataset.create([])
        run = Run("a", dataset.content_hash, scorer.content_hash, "m", ())
        result = compare_runs(run, run)
        self.assertEqual(result.verdict, Verdict.UNDETERMINED)
        self.assertTrue(math.isnan(result.delta))

    def test_world_model_reference_exercises_all_four_scores(self):
        scores = world_model_reference_scores()
        self.assertEqual(
            {key for key in scores if key.startswith("wm/")},
            {"wm/drift", "wm/grounding", "wm/memory", "wm/utility"},
        )
        self.assertEqual(scores["wm/memory"]["occlusion_consistency"], 1.0)

    def test_multiple_metric_correction_widens_interval(self):
        before, after = demo_runs()
        one = compare_runs(before, after, metric_count=1)
        four = compare_runs(before, after, metric_count=4)
        self.assertLess(four.ci_low, one.ci_low)
        self.assertGreater(four.ci_high, one.ci_high)

    def test_duplicate_sample_ids_are_rejected(self):
        before, after = demo_runs()
        duplicated = Run(
            run_id=after.run_id,
            dataset_hash=after.dataset_hash,
            scorer_hash=after.scorer_hash,
            model_id=after.model_id,
            samples=(after.samples[0], after.samples[0], *after.samples[2:]),
        )
        with self.assertRaisesRegex(ValueError, "duplicate sample IDs"):
            compare_runs(before, duplicated)

    def test_changed_sample_definition_is_rejected(self):
        before, after = demo_runs()
        changed = replace(
            after.samples[0],
            reference="lookup",
        )
        changed_run = replace(after, samples=(changed, *after.samples[1:]))
        with self.assertRaisesRegex(ValueError, "sample definition differs"):
            compare_runs(before, changed_run)

    def test_non_finite_score_cannot_pass_a_gate(self):
        before, after = demo_runs()
        invalid = replace(
            after.samples[0],
            scores={"accuracy": math.nan},
        )
        invalid_run = replace(after, samples=(invalid, *after.samples[1:]))
        with self.assertRaisesRegex(ValueError, "non-finite"):
            compare_runs(before, invalid_run)

    def test_gate_parameters_are_validated(self):
        before, after = demo_runs()
        with self.assertRaisesRegex(ValueError, "alpha"):
            compare_runs(before, after, alpha=1.0)
        with self.assertRaisesRegex(ValueError, "tolerance"):
            compare_runs(before, after, tolerance=-0.01)


class ReportTests(unittest.TestCase):
    def test_report_emits_interactive_bench_with_fixture_evidence(self):
        before, after = demo_runs()
        comparison = compare_runs(before, after)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "index.html"
            write_demo_report(target, before, after, comparison)
            document = target.read_text()
            payload = json.loads((target.parent / "comparison.json").read_text())
        self.assertIn('id="run-form"', document)
        self.assertIn('id="tolerance"', document)
        self.assertIn('id="sample-plate"', document)
        self.assertIn('id="score-chart"', document)
        self.assertIn('id="export-button"', document)
        self.assertIn('data-filter="improved"', document)
        self.assertIn('value="scorer-drift"', document)
        self.assertIn('id="candidate-scorer-pin"', document)
        self.assertIn('id="recover-button" hidden', document)
        self.assertIn('id="export-button" disabled', document)
        self.assertEqual(document.count("window.ASSAY_DATA"), 1)
        self.assertEqual(len(payload["samples"]), 100)
        self.assertEqual(len(payload["comparison"]["regressions"]), 12)
        self.assertEqual(payload["comparison"]["verdict"], "BLOCKED")

    def test_report_pairs_reordered_candidate_samples_by_id(self):
        before, after = demo_runs()
        reordered = Run(
            run_id=after.run_id,
            dataset_hash=after.dataset_hash,
            scorer_hash=after.scorer_hash,
            model_id=after.model_id,
            samples=tuple(reversed(after.samples)),
        )
        comparison = compare_runs(before, reordered)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "index.html"
            write_demo_report(target, before, reordered, comparison)
            payload = json.loads((target.parent / "comparison.json").read_text())
        first = payload["samples"][0]
        self.assertEqual(first["sample_id"], "sample-000")
        self.assertEqual(first["reference"], "search")
        self.assertEqual(first["candidate_prediction"], "lookup")

    def test_report_escapes_untrusted_sample_text_in_inline_data(self):
        before, after = demo_runs()
        tainted_sample = replace(
            before.samples[0],
            context={"request": "</script><script>alert('specimen')</script>"},
        )
        tainted_before = replace(
            before,
            samples=(tainted_sample, *before.samples[1:]),
        )
        tainted_candidate_sample = replace(
            after.samples[0],
            context=tainted_sample.context,
        )
        tainted_after = replace(
            after,
            samples=(tainted_candidate_sample, *after.samples[1:]),
        )
        comparison = compare_runs(tainted_before, tainted_after)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "index.html"
            write_demo_report(target, tainted_before, tainted_after, comparison)
            document = target.read_text()
        self.assertNotIn("</script><script>alert", document)
        self.assertIn("\\u003c/script\\u003e", document)

    def test_interactive_contract_error_and_recovery_are_wired(self):
        project_root = Path(__file__).resolve().parents[1]
        script = (project_root / "docs" / "demo" / "app.js").read_text()
        self.assertIn("function renderContractError()", script)
        self.assertIn('"MERGE WITHHELD"', script)
        self.assertIn('"CONTRACT ERROR"', script)
        self.assertIn('$("#export-button").disabled = true', script)
        self.assertIn('$("#recover-button").addEventListener("click"', script)
        self.assertIn('$("#candidate").value = "prompt-v2"', script)


if __name__ == "__main__":
    unittest.main()
