"""Documented GET only, with a pace limit and bounded 429 retries. Redirects are not followed."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from ats_pay_range_audit import __version__
from ats_pay_range_audit.errors import FetchError, UsageError
from ats_pay_range_audit.urls import assert_fetch_url

MAX_BODY_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_RETRIES = 3
MAX_RETRY_SLEEP = 30.0

MIN_INTERVAL = {
    "greenhouse": 0.5,
    "ashby": 0.5,
    "lever": 1.0,
}

USER_AGENT = f"ats-pay-range-audit/{__version__} (read-only public job-board audit)"


@dataclass
class RawResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FetchError("redirect_blocked", f"redirect status {code} was not followed")


class LiveRaw:
    """One GET via urllib. No POST helper exists."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        self.opener = urllib.request.build_opener(_RejectRedirects)

    def get(self, url: str, timeout: float | None = None) -> RawResponse:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with self.opener.open(request, timeout=timeout or self.timeout) as response:
                return _read_response(response.status, response.headers, response)
        except FetchError:
            raise
        except urllib.error.HTTPError as exc:
            try:
                return _read_response(exc.code, exc.headers, exc)
            finally:
                exc.close()
        except TimeoutError as exc:
            raise FetchError("timeout", "request timed out") from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise FetchError("timeout", "request timed out") from exc
            raise FetchError("http_error", "request failed before a JSON body") from exc


class PoliteSession:
    def __init__(
        self,
        raw,
        *,
        sleeper: Callable[[float], None],
        clock: Callable[[], float],
        min_intervals: dict[str, float] | None = None,
        pace: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.raw = raw
        self.sleeper = sleeper
        self.clock = clock
        self.min_intervals = dict(MIN_INTERVAL if min_intervals is None else min_intervals)
        self._clamp_intervals()
        self.pace = pace
        self.max_retries = max_retries
        self.last: dict[str, float] = {}
        self.calls: list[str] = []

    def _clamp_intervals(self) -> None:
        for provider, floor in MIN_INTERVAL.items():
            current = float(self.min_intervals.get(provider, floor))
            if current < 0:
                raise UsageError("interval cannot be negative")
            self.min_intervals[provider] = max(floor, current)

    def get_json(self, url: str, provider: str):
        assert_fetch_url(url, provider)
        attempts = self.max_retries + 1
        last_status = None
        for attempt in range(attempts):
            self._pace(provider)
            self.calls.append(url)
            try:
                raw = self.raw.get(url, None)
            except FetchError:
                raise
            except TimeoutError as exc:
                raise FetchError("timeout", "request timed out") from exc
            last_status = raw.status
            if raw.status == 429 and attempt < self.max_retries:
                delay = _retry_delay(raw.headers, attempt)
                self.sleeper(delay)
                self.last[provider] = self.clock()
                continue
            return _interpret(raw, provider)
        raise FetchError("http_429", f"HTTP 429 from {provider} after retries")

    def _pace(self, provider: str) -> None:
        if not self.pace:
            return
        if provider in self.last:
            need = self.min_intervals[provider] - (self.clock() - self.last[provider])
            if need > 0:
                self.sleeper(need)
        self.last[provider] = self.clock()


def resolved_intervals(override: float | None) -> dict[str, float]:
    intervals = dict(MIN_INTERVAL)
    if override is None:
        return intervals
    if override < 0:
        raise UsageError("--min-interval cannot be negative")
    for provider, floor in MIN_INTERVAL.items():
        intervals[provider] = max(floor, float(override))
    return intervals


def _read_response(status: int, headers, stream) -> RawResponse:
    payload = stream.read(MAX_BODY_BYTES + 1)
    if len(payload) > MAX_BODY_BYTES:
        raise FetchError("parse_error", "response exceeded the 8 MiB body limit")
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    return RawResponse(status, lowered, payload)


def _interpret(raw: RawResponse, provider: str):
    if raw.status in (301, 302, 303, 307, 308):
        raise FetchError("redirect_blocked", f"redirect status {raw.status} was not followed")
    if raw.status == 429:
        raise FetchError("http_429", f"HTTP 429 from {provider}")
    if raw.status != 200:
        raise FetchError("http_error", f"HTTP {raw.status} from {provider}")
    try:
        text = raw.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FetchError("parse_error", "response was not UTF-8 JSON") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError("parse_error", "response was not JSON") from exc


def _retry_delay(headers: dict[str, str], attempt: int) -> float:
    raw = headers.get("retry-after", "")
    text = raw.strip()
    if text.isdigit():
        delay = float(text)
    else:
        delay = float(2**attempt)
    if delay < 0:
        delay = 0.0
    return min(MAX_RETRY_SLEEP, delay)
