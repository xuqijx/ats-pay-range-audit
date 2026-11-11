"""Offline response books. Every file shipped in fixtures/ is fictional."""

from __future__ import annotations

import json
from pathlib import Path

from ats_pay_range_audit.errors import UsageError
from ats_pay_range_audit.http_client import RawResponse


class FixtureRaw:
    def __init__(self, path: Path, provider: str):
        self.path = Path(path)
        self.provider = provider
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UsageError(f"could not read fixture {self.path}") from exc
        if not isinstance(payload, dict):
            raise UsageError(f"fixture {self.path} was not a JSON object")
        if payload.get("provider") != provider:
            raise UsageError(f"fixture {self.path} is not a {provider} fixture")
        self.mode = payload.get("mode") or "mapped"
        self.disclaimer = payload.get("disclaimer")
        self.fictional = payload.get("fictional")
        self._payload = payload
        self._script = list(payload.get("script") or [])
        self._queues: dict[str, list] = {}
        self.calls: list[str] = []

    def get(self, url: str, timeout: float | None = None) -> RawResponse:
        self.calls.append(url)
        if self.mode == "script":
            return self._next_script()
        if self.provider == "greenhouse":
            return self._greenhouse(url)
        body = self._payload.get("body")
        if body is None:
            raise UsageError(f"fixture {self.path} has no body")
        return _as_response(body)

    def _next_script(self) -> RawResponse:
        if not self._script:
            return RawResponse(429, {"retry-after": "0"}, b'{"error":"rate limit"}')
        item = self._script.pop(0)
        if not isinstance(item, dict):
            raise UsageError(f"fixture {self.path} has a script entry that is not an object")
        return _as_response(item)

    def _greenhouse(self, url: str) -> RawResponse:
        job_id = _greenhouse_detail_id(url)
        if job_id is None:
            listed = self._payload.get("list")
            if listed is None:
                raise UsageError(f"fixture {self.path} has no list")
            return _as_response(listed)
        details = self._payload.get("details")
        if not isinstance(details, dict) or job_id not in details:
            return RawResponse(404, {}, b'{"status":404,"error":"fixture detail missing"}')
        detail = details[job_id]
        if isinstance(detail, list):
            queue = self._queues.setdefault(job_id, list(detail))
            if not queue:
                return RawResponse(429, {"retry-after": "0"}, b'{"error":"rate limit"}')
            return _as_response(queue.pop(0))
        return _as_response(detail)


def _greenhouse_detail_id(url: str) -> str | None:
    path = url.split("?", 1)[0]
    marker = "/jobs/"
    if marker not in path:
        return None
    job_id = path.rsplit(marker, 1)[1]
    if not job_id or "/" in job_id:
        return None
    return job_id


def _as_response(item: object) -> RawResponse:
    if isinstance(item, dict) and "status" in item and "body" in item:
        status = item["status"]
        headers = {str(key).lower(): str(value) for key, value in dict(item.get("headers") or {}).items()}
        body = item["body"]
    else:
        status = 200
        headers = {}
        body = item
    if isinstance(body, bytes):
        encoded = body
    else:
        encoded = json.dumps(body).encode("utf-8")
    if not isinstance(status, int):
        raise UsageError("fixture status must be an integer")
    return RawResponse(status, headers, encoded)
