import math
import unittest

from assay.core import (
    Dataset,
    RunStore,
    ScorerSpec,
    compare_runs,
    demo_runs,
    world_model_reference_scores,
)
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


if __name__ == "__main__":
    unittest.main()
