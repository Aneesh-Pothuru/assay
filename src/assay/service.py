from __future__ import annotations

import json
import sys
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import unquote, urlsplit

from .core import (
    RunStore,
    ScorerSpec,
    canonical_hash,
    compare_runs,
    demo_runs,
    utc_now,
)
from .schemas.loopkit import Run


API_VERSION = "v1"
DEFAULT_MAX_BODY_BYTES = 2 * 1024 * 1024


class APIError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def _number(
    payload: dict[str, Any],
    name: str,
    default: float,
    *,
    integer: bool = False,
) -> float | int:
    value = payload.get(name, default)
    expected = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, expected):
        raise APIError(422, "invalid_request", f"{name} must be numeric")
    return int(value) if integer else float(value)


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise APIError(422, "invalid_request", f"{name} must be a non-empty string")
    return value


def _error_for_value_error(error: ValueError) -> APIError:
    message = str(error)
    if "different dataset versions" in message or "dataset hash mismatch" in message:
        return APIError(409, "dataset_mismatch", message)
    if "scorer" in message and ("mismatch" in message or "cross-" in message):
        return APIError(409, "scorer_mismatch", message)
    if "sample" in message and (
        "differ" in message or "duplicate" in message or "already exists" in message
    ):
        return APIError(409, "sample_contract_mismatch", message)
    if "already exists with different content" in message:
        return APIError(409, "immutable_record_conflict", message)
    return APIError(422, "invalid_contract", message)


class EvaluationService:
    """Application service that keeps the HTTP and CLI paths on one engine."""

    def __init__(self, store: RunStore) -> None:
        self.store = store

    def ingest_run(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(envelope, dict):
            raise APIError(422, "invalid_request", "request body must be an object")
        try:
            run = Run.from_dict(envelope.get("run"))
            scorer = ScorerSpec.from_payload(envelope.get("scorer"))
            created = self.store.save(run, scorer)
        except (TypeError, ValueError) as error:
            raise _error_for_value_error(ValueError(str(error))) from error
        return {
            "schema_version": "assay.run-receipt.v1",
            "run_id": run.run_id,
            "created": created,
            "dataset_hash": run.dataset_hash,
            "scorer_hash": run.scorer_hash,
            "sample_count": len(run.samples),
        }

    def seed_demo(self) -> list[dict[str, Any]]:
        scorer = ScorerSpec.create("exact_tool_selection", "1.0.0")
        receipts = []
        for run in demo_runs():
            receipts.append(
                self.ingest_run({"run": run.to_dict(), "scorer": scorer.to_dict()})
            )
        return receipts

    def compare(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise APIError(422, "invalid_request", "request body must be an object")
        baseline_id = _required_text(request, "baseline_run_id")
        candidate_id = _required_text(request, "candidate_run_id")
        metric = request.get("metric", "accuracy")
        if not isinstance(metric, str) or not metric:
            raise APIError(422, "invalid_request", "metric must be a non-empty string")
        alpha = _number(request, "alpha", 0.05)
        metric_count = _number(request, "metric_count", 1, integer=True)
        tolerance = _number(request, "tolerance", 0.0)
        try:
            baseline = self.store.get(baseline_id)
        except KeyError as error:
            raise APIError(404, "run_not_found", f"baseline run {baseline_id} was not found") from error
        try:
            candidate = self.store.get(candidate_id)
        except KeyError as error:
            raise APIError(404, "run_not_found", f"candidate run {candidate_id} was not found") from error
        try:
            comparison = compare_runs(
                baseline,
                candidate,
                metric,
                alpha=float(alpha),
                metric_count=int(metric_count),
                tolerance=float(tolerance),
            )
        except KeyError as error:
            raise APIError(
                422,
                "metric_not_found",
                f"metric {metric} is missing from one or more samples",
            ) from error
        except ValueError as error:
            raise _error_for_value_error(error) from error

        identity = {
            "baseline_run_id": baseline_id,
            "candidate_run_id": candidate_id,
            "metric": metric,
            "alpha": float(alpha),
            "metric_count": int(metric_count),
            "tolerance": float(tolerance),
        }
        comparison_id = "cmp_" + canonical_hash(identity).split(":", 1)[1][:24]
        try:
            return self.store.get_comparison(comparison_id)
        except KeyError:
            pass

        baseline_by_id = {sample.sample_id: sample for sample in baseline.samples}
        candidate_by_id = {sample.sample_id: sample for sample in candidate.samples}
        samples = []
        for sample_id in sorted(baseline_by_id):
            before = baseline_by_id[sample_id]
            after = candidate_by_id[sample_id]
            before_score = before.scores[metric]
            after_score = after.scores[metric]
            status = (
                "regressed"
                if after_score < before_score
                else "improved"
                if after_score > before_score
                else "held"
            )
            samples.append(
                {
                    "sample_id": sample_id,
                    "context": before.context,
                    "action": before.action,
                    "reference": before.reference,
                    "baseline_prediction": before.prediction,
                    "candidate_prediction": after.prediction,
                    "baseline_score": before_score,
                    "candidate_score": after_score,
                    "status": status,
                }
            )
        evidence = {
            "schema_version": "assay.comparison-evidence.v1",
            "comparison_id": comparison_id,
            "created_at": utc_now(),
            "baseline_run_id": baseline_id,
            "candidate_run_id": candidate_id,
            "dataset_hash": baseline.dataset_hash,
            "scorer_hash": baseline.scorer_hash,
            "parameters": identity,
            "comparison": comparison.to_dict(),
            "samples": samples,
            "scope": (
                "Computed locally by the installed ASSAY service from immutable "
                "version-pinned runs; no provider execution is implied."
            ),
        }
        self.store.save_comparison(evidence)
        return evidence


OPENAPI = {
    "openapi": "3.1.0",
    "info": {
        "title": "ASSAY local evaluation API",
        "version": "1.0.0",
        "description": "Keyless local run ingestion, comparison, and evidence retrieval.",
    },
    "paths": {
        "/healthz": {"get": {"summary": "Liveness"}},
        "/readyz": {"get": {"summary": "SQLite readiness"}},
        "/api/v1/runs": {
            "get": {"summary": "List immutable runs"},
            "post": {"summary": "Ingest a run and verified scorer contract"},
        },
        "/api/v1/runs/{run_id}": {"get": {"summary": "Get a run"}},
        "/api/v1/comparisons": {
            "get": {"summary": "List evidence records"},
            "post": {"summary": "Compare two persisted runs with the ASSAY engine"},
        },
        "/api/v1/comparisons/{comparison_id}": {
            "get": {"summary": "Get a durable evidence record"}
        },
    },
}


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def create_server(
    service: EvaluationService,
    host: str,
    port: int,
    *,
    cors_origin: str | None = None,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ASSAY/0.2"

        def _request_id(self) -> str:
            return self.headers.get("X-Request-ID") or uuid.uuid4().hex

        def _headers(
            self,
            status: int,
            content_type: str,
            length: int,
            request_id: str,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("X-Request-ID", request_id)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
            )
            if cors_origin:
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("Vary", "Origin")
            self.end_headers()

        def _send_json(
            self, status: int, payload: Any, request_id: str | None = None
        ) -> None:
            body = _json_bytes(payload)
            self._headers(
                status,
                "application/json; charset=utf-8",
                len(body),
                request_id or self._request_id(),
            )
            self.wfile.write(body)

        def _send_asset(self, name: str, content_type: str) -> None:
            request_id = self._request_id()
            try:
                body = resources.files("assay.web").joinpath(name).read_bytes()
            except (FileNotFoundError, ModuleNotFoundError):
                self._send_error(
                    APIError(500, "asset_missing", f"packaged asset {name} is missing"),
                    request_id,
                )
                return
            self._headers(200, content_type, len(body), request_id)
            self.wfile.write(body)

        def _send_error(self, error: APIError, request_id: str) -> None:
            self._send_json(
                error.status,
                {
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                        "retryable": error.status >= 500,
                    },
                    "request_id": request_id,
                },
                request_id,
            )

        def _read_json(self) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "")
            if not content_type.lower().startswith("application/json"):
                raise APIError(415, "unsupported_media_type", "Content-Type must be application/json")
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise APIError(411, "length_required", "Content-Length is required")
            try:
                length = int(raw_length)
            except ValueError as error:
                raise APIError(400, "invalid_content_length", "Content-Length is invalid") from error
            if length < 0 or length > max_body_bytes:
                raise APIError(
                    413,
                    "payload_too_large",
                    f"request body exceeds {max_body_bytes} bytes",
                )
            try:
                payload = json.loads(
                    self.rfile.read(length).decode("utf-8"),
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError(f"invalid JSON constant {value}")
                    ),
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                raise APIError(400, "invalid_json", "request body is not valid strict JSON") from error
            if not isinstance(payload, dict):
                raise APIError(422, "invalid_request", "request body must be an object")
            return payload

        def do_OPTIONS(self) -> None:
            request_id = self._request_id()
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("X-Request-ID", request_id)
            if cors_origin:
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Request-ID")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Vary", "Origin")
            self.end_headers()

        def do_GET(self) -> None:
            request_id = self._request_id()
            path = unquote(urlsplit(self.path).path)
            try:
                if path == "/":
                    self.send_response(303)
                    self.send_header("Location", "/app/")
                    self.send_header("Content-Length", "0")
                    self.send_header("X-Request-ID", request_id)
                    self.end_headers()
                    return
                if path in {"/app", "/app/"}:
                    self._send_asset("index.html", "text/html; charset=utf-8")
                    return
                if path == "/app/app.css":
                    self._send_asset("app.css", "text/css; charset=utf-8")
                    return
                if path == "/app/app.js":
                    self._send_asset("app.js", "text/javascript; charset=utf-8")
                    return
                if path == "/healthz":
                    self._send_json(200, {"status": "ok"}, request_id)
                    return
                if path == "/readyz":
                    ready = service.store.is_ready()
                    self._send_json(
                        200 if ready else 503,
                        {"status": "ready" if ready else "not_ready"},
                        request_id,
                    )
                    return
                if path == "/api/v1/openapi.json":
                    self._send_json(200, OPENAPI, request_id)
                    return
                if path == "/api/v1/runs":
                    self._send_json(200, {"runs": service.store.list_runs()}, request_id)
                    return
                if path.startswith("/api/v1/runs/"):
                    run_id = path.removeprefix("/api/v1/runs/")
                    try:
                        payload = service.store.get_payload(run_id)
                    except KeyError as error:
                        raise APIError(404, "run_not_found", f"run {run_id} was not found") from error
                    self._send_json(200, payload, request_id)
                    return
                if path == "/api/v1/comparisons":
                    self._send_json(
                        200,
                        {"comparisons": service.store.list_comparisons()},
                        request_id,
                    )
                    return
                if path.startswith("/api/v1/comparisons/"):
                    comparison_id = path.removeprefix("/api/v1/comparisons/")
                    try:
                        payload = service.store.get_comparison(comparison_id)
                    except KeyError as error:
                        raise APIError(
                            404,
                            "comparison_not_found",
                            f"comparison {comparison_id} was not found",
                        ) from error
                    self._send_json(200, payload, request_id)
                    return
                raise APIError(404, "not_found", f"route {path} was not found")
            except APIError as error:
                self._send_error(error, request_id)
            except Exception as error:  # pragma: no cover - defensive server boundary
                self._send_error(
                    APIError(500, "internal_error", "unexpected server error"),
                    request_id,
                )
                print(f"ASSAY internal error {request_id}: {error!r}", file=sys.stderr)

        def do_POST(self) -> None:
            request_id = self._request_id()
            path = unquote(urlsplit(self.path).path)
            try:
                payload = self._read_json()
                if path == "/api/v1/runs":
                    result = service.ingest_run(payload)
                    self._send_json(201 if result["created"] else 200, result, request_id)
                    return
                if path == "/api/v1/comparisons":
                    result = service.compare(payload)
                    self._send_json(200, result, request_id)
                    return
                raise APIError(404, "not_found", f"route {path} was not found")
            except APIError as error:
                self._send_error(error, request_id)
            except Exception as error:  # pragma: no cover - defensive server boundary
                self._send_error(
                    APIError(500, "internal_error", "unexpected server error"),
                    request_id,
                )
                print(f"ASSAY internal error {request_id}: {error!r}", file=sys.stderr)

        def log_message(self, format: str, *args: object) -> None:
            print(
                json.dumps(
                    {
                        "component": "assay.http",
                        "client": self.client_address[0],
                        "message": format % args,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )

    return ThreadingHTTPServer((host, port), Handler)
