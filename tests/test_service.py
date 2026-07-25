import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from assay.core import Dataset, RunStore, ScorerSpec, demo_runs
from assay.schemas.loopkit import Run
from assay.service import APIError, EvaluationService, create_server


def request_json(url, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers)
    try:
        response = urlopen(request, timeout=3)
    except HTTPError as error:
        try:
            return error.code, json.loads(error.read()), error.headers
        finally:
            error.close()
    return response.status, json.load(response), response.headers


class PersistenceJourneyTests(unittest.TestCase):
    def test_seed_compare_restart_and_retrieve_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "nested" / "assay.sqlite"
            with RunStore(db) as store:
                service = EvaluationService(store)
                receipts = service.seed_demo()
                evidence = service.compare(
                    {
                        "baseline_run_id": "demo-baseline",
                        "candidate_run_id": "demo-candidate",
                        "metric": "accuracy",
                        "tolerance": 0,
                    }
                )
                comparison_id = evidence["comparison_id"]
                self.assertEqual([item["created"] for item in receipts], [True, True])
                self.assertEqual(evidence["comparison"]["verdict"], "BLOCKED")
                self.assertEqual(len(evidence["comparison"]["regressions"]), 12)
                self.assertEqual(len(evidence["samples"]), 100)
            with RunStore(db) as reopened:
                persisted = reopened.get_comparison(comparison_id)
                self.assertEqual(persisted["comparison_id"], comparison_id)
                self.assertEqual(persisted["comparison"]["verdict"], "BLOCKED")
                self.assertEqual(len(reopened.list_runs()), 2)

    def test_run_ids_are_immutable_but_identical_retries_are_idempotent(self):
        before, _ = demo_runs()
        scorer = ScorerSpec.create("exact_tool_selection", "1.0.0")
        with RunStore() as store:
            self.assertTrue(store.save(before, scorer))
            self.assertFalse(store.save(before, scorer))
            changed = replace(before, model_id="different-model")
            with self.assertRaisesRegex(ValueError, "different content"):
                store.save(changed, scorer)

    def test_empty_paired_runs_persist_an_undetermined_json_record(self):
        scorer = ScorerSpec.create("accuracy", "1.0.0")
        dataset = Dataset.create([])
        first = Run("empty-a", dataset.content_hash, scorer.content_hash, "a", ())
        second = Run("empty-b", dataset.content_hash, scorer.content_hash, "b", ())
        with RunStore() as store:
            service = EvaluationService(store)
            service.ingest_run({"run": first.to_dict(), "scorer": scorer.to_dict()})
            service.ingest_run({"run": second.to_dict(), "scorer": scorer.to_dict()})
            evidence = service.compare(
                {
                    "baseline_run_id": "empty-a",
                    "candidate_run_id": "empty-b",
                }
            )
            self.assertEqual(evidence["comparison"]["verdict"], "UNDETERMINED")
            self.assertIsNone(evidence["comparison"]["delta"])
            json.dumps(evidence, allow_nan=False)

    def test_cross_scorer_request_is_a_hard_error_and_stores_no_evidence(self):
        before, candidate = demo_runs()
        scorer_v1 = ScorerSpec.create("exact_tool_selection", "1.0.0")
        scorer_v2 = ScorerSpec.create("exact_tool_selection", "2.0.0")
        incompatible = replace(
            candidate,
            run_id="incompatible-candidate",
            scorer_hash=scorer_v2.content_hash,
        )
        with RunStore() as store:
            service = EvaluationService(store)
            service.ingest_run({"run": before.to_dict(), "scorer": scorer_v1.to_dict()})
            service.ingest_run(
                {"run": incompatible.to_dict(), "scorer": scorer_v2.to_dict()}
            )
            with self.assertRaises(APIError) as raised:
                service.compare(
                    {
                        "baseline_run_id": before.run_id,
                        "candidate_run_id": incompatible.run_id,
                    }
                )
            self.assertEqual(raised.exception.status, 409)
            self.assertEqual(raised.exception.code, "scorer_mismatch")
            self.assertEqual(store.list_comparisons(), [])

    def test_ingest_verifies_dataset_and_scorer_content_hashes(self):
        before, _ = demo_runs()
        scorer = ScorerSpec.create("exact_tool_selection", "1.0.0")
        bad_run = replace(before, dataset_hash="sha256:" + "0" * 64)
        with RunStore() as store:
            service = EvaluationService(store)
            with self.assertRaises(APIError) as dataset_error:
                service.ingest_run(
                    {"run": bad_run.to_dict(), "scorer": scorer.to_dict()}
                )
            self.assertEqual(dataset_error.exception.code, "dataset_mismatch")
            bad_scorer = {**scorer.to_dict(), "version": "9.9.9"}
            with self.assertRaises(APIError) as scorer_error:
                service.ingest_run(
                    {"run": before.to_dict(), "scorer": bad_scorer}
                )
            self.assertEqual(scorer_error.exception.code, "scorer_mismatch")


class HTTPJourneyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = RunStore(Path(self.directory.name) / "assay.sqlite")
        self.service = EvaluationService(self.store)
        self.service.seed_demo()
        self.server = create_server(self.service, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.store.close()
        self.directory.cleanup()

    def test_health_readiness_packaged_ui_and_security_headers(self):
        status, health, headers = request_json(self.base + "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, ready, _ = request_json(self.base + "/readyz")
        self.assertEqual((status, ready["status"]), (200, "ready"))
        response = urlopen(self.base + "/app/", timeout=3)
        document = response.read().decode()
        self.assertIn("Comparison instrument", document)
        self.assertEqual(response.headers["Content-Security-Policy"].split(";")[0], "default-src 'self'")

    def test_http_compare_persists_retrievable_ui_evidence(self):
        status, runs, _ = request_json(self.base + "/api/v1/runs")
        self.assertEqual(status, 200)
        self.assertEqual(len(runs["runs"]), 2)
        status, evidence, _ = request_json(
            self.base + "/api/v1/comparisons",
            {
                "baseline_run_id": "demo-baseline",
                "candidate_run_id": "demo-candidate",
                "metric": "accuracy",
                "tolerance": 0,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(evidence["comparison"]["verdict"], "BLOCKED")
        comparison_id = evidence["comparison_id"]
        status, fetched, _ = request_json(
            self.base + f"/api/v1/comparisons/{comparison_id}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(fetched, evidence)

    def test_http_contract_error_is_structured_and_does_not_create_evidence(self):
        _, candidate = demo_runs()
        scorer_v2 = ScorerSpec.create("exact_tool_selection", "2.0.0")
        incompatible = replace(
            candidate,
            run_id="http-incompatible",
            scorer_hash=scorer_v2.content_hash,
        )
        status, _, _ = request_json(
            self.base + "/api/v1/runs",
            {"run": incompatible.to_dict(), "scorer": scorer_v2.to_dict()},
        )
        self.assertEqual(status, 201)
        status, payload, _ = request_json(
            self.base + "/api/v1/comparisons",
            {
                "baseline_run_id": "demo-baseline",
                "candidate_run_id": "http-incompatible",
            },
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "scorer_mismatch")
        status, comparisons, _ = request_json(self.base + "/api/v1/comparisons")
        self.assertEqual(status, 200)
        self.assertEqual(comparisons["comparisons"], [])


if __name__ == "__main__":
    unittest.main()
