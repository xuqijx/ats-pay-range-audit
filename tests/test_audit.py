"""Offline tests. None of these open a socket."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ats_pay_range_audit.audit import report_has_errors, run_audit
from ats_pay_range_audit.boards import Board, load_boards
from ats_pay_range_audit.classify import (
    classify_ashby_compensation,
    classify_ashby_job,
    classify_greenhouse_detail,
    classify_lever_posting,
)
from ats_pay_range_audit import __version__
from ats_pay_range_audit.cli import main
from ats_pay_range_audit.diffing import diff_snapshots
from ats_pay_range_audit.errors import FetchError, UsageError
from ats_pay_range_audit.fixtures import FixtureRaw
from ats_pay_range_audit.http_client import (
    MAX_BODY_BYTES,
    LiveRaw,
    PoliteSession,
    RawResponse,
    _RejectRedirects,
    _read_response,
    resolved_intervals,
)
from ats_pay_range_audit.money import cents_to_major, whole_cents
from ats_pay_range_audit.snapshot import atomic_write_text, load_snapshot
from ats_pay_range_audit.urls import ashby_board_url, greenhouse_detail_url, greenhouse_list_url, lever_board_url

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
EXAMPLES = ROOT / "examples"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptRaw:
    def __init__(self, responses: list[RawResponse]):
        self.responses = list(responses)
        self.calls: list[str] = []

    def get(self, url: str, timeout: float | None = None) -> RawResponse:
        self.calls.append(url)
        if not self.responses:
            return RawResponse(429, {"retry-after": "0"}, b"{}")
        return self.responses.pop(0)


def _audit(fixture: str, provider: str, board: str, *, max_details: int = 500, region: str = "global"):
    raw = FixtureRaw(FIXTURES / fixture, provider)
    session = PoliteSession(raw, sleeper=lambda _seconds: None, clock=lambda: 0.0, pace=False)
    spec = Board(provider, board, f"{board} (fictional)", region, FIXTURES / fixture)
    report = run_audit(
        [spec],
        lambda _board: session,
        generated_at="2026-11-11T00:00:00Z",
        max_details=max_details,
        network=False,
    )
    return report, session


def _cli(argv: list[str], capsys) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as caught:
        main(argv)
    captured = capsys.readouterr()
    return int(caught.value.code), captured.out, captured.err


def test_packaged_fixtures_are_fictional_and_not_live_boards():
    banned = ("stripe", "ramp", "figma", "leverdemo", "vaulttec")
    files = list(FIXTURES.rglob("*.json"))
    assert files
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload.get("fictional") is True
        text = path.read_text(encoding="utf-8").lower()
        for word in banned:
            assert word not in text


def test_package_has_no_application_post():
    text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py"))
    assert 'method="POST"' not in text
    assert "method='POST'" not in text
    assert "/applications" not in text


def test_ashby_all_ranges_are_complete_and_sorted():
    report, session = _audit("ashby-all-ranges.json", "ashby", "hearth-and-quill")
    assert report_has_errors(report) is False
    coverage = report["coverage"]
    assert coverage["numerator"] == 2
    assert coverage["denominator"] == 2
    assert coverage["ratio"] == "2/2"
    assert coverage["percent"] == 100
    assert coverage["unknown"] == 0
    assert [job["job_id"] for job in report["jobs"]] == ["job-a", "job-c"]
    first = report["jobs"][0]
    assert first["ranges"][0]["min"] == 80000
    assert first["ranges"][0]["max"] == 95000
    assert first["ranges"][0]["currency"] == "USD"
    assert first["ranges"][0]["period"] == "1 YEAR"
    second = report["jobs"][1]["ranges"]
    assert len(second) == 1
    assert second[0]["min"] == 90000
    assert second[0]["max"] == 110000
    assert "includeCompensation=true" in session.calls[0]
    assert session.calls[0].startswith("https://api.ashbyhq.com/posting-api/job-board/hearth-and-quill?")


def test_ashby_empty_object_null_summary_and_unknown_are_distinct():
    report, _session = _audit("ashby-variants.json", "ashby", "hearth-and-quill")
    by_id = {job["job_id"]: job for job in report["jobs"]}
    assert by_id["empty-object"]["observation"] == "explicit_empty"
    assert by_id["empty-object"]["reason"] == "empty_object"
    assert by_id["empty-object"]["ranges"] == []
    assert by_id["null-comp"]["reason"] == "null"
    assert by_id["summary-only"]["reason"] == "summary_only"
    assert by_id["summary-only"]["summary"] == "SUMMARY-SENTINEL-81K"
    assert by_id["summary-only"]["ranges"] == []
    assert by_id["equity-only"]["reason"] == "no_salary_component"
    assert by_id["equity-only"]["ranges"] == []
    assert by_id["missing-key"]["observation"] == "unknown"
    assert by_id["missing-key"]["reason"] == "field_not_in_response"
    assert by_id["valid-salary"]["observation"] == "valid"
    assert by_id["valid-salary"]["ranges"][0]["currency"] == "EUR"
    assert by_id["valid-salary"]["ranges"][0]["period"] == "1 HOUR"
    assert by_id["valid-salary"]["ranges"][0]["min"] == 40
    assert by_id["valid-salary"]["ranges"][0]["max"] is None
    blob = json.dumps(report)
    assert "515151" not in blob
    coverage = report["coverage"]
    assert coverage["numerator"] == 1
    assert coverage["denominator"] == 5
    assert coverage["unknown"] == 1
    assert coverage["ratio"] == "1/5"
    assert "ignored_top_level_compensation" in report["boards"][0]["notes"]


def test_greenhouse_empty_key_is_not_a_request_failure_and_ignores_the_list():
    report, session = _audit("greenhouse-key-present-empty.json", "greenhouse", "northwind-fictional")
    assert report_has_errors(report) is False
    assert report["coverage"]["ratio"] == "0/2"
    assert report["coverage"]["percent"] == 0
    assert report["coverage"]["error"] == 0
    assert {job["reason"] for job in report["jobs"]} == {"empty_array"}
    assert {job["structured_range"] for job in report["jobs"]} == {"absent"}
    blob = json.dumps(report)
    assert "42424200" not in blob
    assert "CONTENT-SENTINEL-77000" not in blob
    assert "ignored_list_pay_fields" in report["boards"][0]["notes"]
    list_calls = [url for url in session.calls if url.endswith("/jobs")]
    detail_calls = [url for url in session.calls if "/jobs/" in url]
    assert len(list_calls) == 1
    assert "pay_transparency" not in list_calls[0]
    assert "pay_input_ranges" not in list_calls[0]
    assert "content=true" not in list_calls[0]
    assert len(detail_calls) == 2
    assert all(url.endswith("?pay_transparency=true") and "pay_input_ranges=" not in url for url in detail_calls)


def test_greenhouse_list_pay_does_not_decide_and_unknown_stays_out_of_the_denominator():
    report, session = _audit("greenhouse-list-must-not-decide.json", "greenhouse", "northwind-fictional")
    by_id = {job["job_id"]: job for job in report["jobs"]}
    assert by_id["10"]["observation"] == "valid"
    assert by_id["10"]["url"] == "https://boards.greenhouse.io/northwind-fictional/jobs/10"
    assert "evil.example" not in json.dumps(report)
    assert "BLURB-SENTINEL-99" not in json.dumps(report)
    currencies = [item["currency"] for item in by_id["10"]["ranges"]]
    assert currencies == ["EUR", "USD"]
    assert by_id["10"]["ranges"][0]["min"] == 20000
    assert by_id["10"]["ranges"][0]["max"] == 10000
    assert by_id["10"]["ranges"][1]["min"] == 50000
    assert by_id["10"]["ranges"][1]["max"] == "50000.50"
    assert by_id["11"]["observation"] == "unknown"
    assert by_id["11"]["reason"] == "field_not_in_response"
    assert by_id["11"]["ranges"] == []
    assert by_id["12"]["observation"] == "valid"
    assert by_id["12"]["ranges"][0]["min"] == 30000
    blob = json.dumps(by_id["11"]) + json.dumps(by_id["12"])
    assert "42424201" not in blob
    assert "43434301" not in blob
    assert report["coverage"]["numerator"] == 2
    assert report["coverage"]["denominator"] == 2
    assert report["coverage"]["unknown"] == 1
    assert report["coverage"]["ratio"] == "2/2"
    assert "list_count_mismatch" in report["boards"][0]["notes"]
    assert [url for url in session.calls if url.endswith("/jobs")][0].endswith("/jobs")

    capped, capped_session = _audit(
        "greenhouse-list-must-not-decide.json",
        "greenhouse",
        "northwind-fictional",
        max_details=1,
    )
    capped_ids = {job["job_id"]: job for job in capped["jobs"]}
    assert capped_ids["10"]["observation"] == "valid"
    assert capped_ids["11"]["observation"] == "unknown"
    assert capped_ids["11"]["reason"] == "detail_budget_exhausted"
    assert capped_ids["12"]["reason"] == "detail_budget_exhausted"
    assert capped["coverage"]["ratio"] == "1/1"
    assert capped["coverage"]["unknown"] == 2
    detail_ids = [url for url in capped_session.calls if "/jobs/" in url]
    assert detail_ids == [
        "https://boards-api.greenhouse.io/v1/boards/northwind-fictional/jobs/10?pay_transparency=true"
    ]


def test_greenhouse_detail_variants_do_not_parse_blurbs():
    assert classify_greenhouse_detail({"pay_input_ranges": None})["reason"] == "null"
    assert classify_greenhouse_detail({"pay_input_ranges": {}})["reason"] == "empty_object"
    assert classify_greenhouse_detail({"pay_input_ranges": []})["reason"] == "empty_array"
    missing = classify_greenhouse_detail({"id": 1, "content": "salary $10"})
    assert missing["observation"] == "unknown"
    assert missing["ranges"] == []
    prose = classify_greenhouse_detail(
        {
            "pay_input_ranges": [
                {"title": "Label", "blurb": "BLURB-SENTINEL-99 $10 to $20", "min_cents": True, "max_cents": False}
            ]
        }
    )
    assert prose["observation"] == "explicit_empty"
    assert prose["reason"] == "no_numeric_bounds"
    assert "BLURB-SENTINEL-99" not in json.dumps(prose)
    weird = classify_greenhouse_detail({"pay_input_ranges": {"min_cents": 100}})
    assert weird["observation"] == "error"
    assert weird["reason"] == "schema_incompatible"
    string_body = classify_greenhouse_detail(["nope"])
    assert string_body["reason"] == "schema_incompatible"


def test_cents_conversion_rejects_bools_and_keeps_fractional_cents():
    assert whole_cents(True) is None
    assert whole_cents(False) is None
    assert cents_to_major(5000000) == 50000
    assert cents_to_major(5000050) == "50000.50"
    assert cents_to_major(None) is None


def test_lever_omitted_field_is_absent_and_description_is_not_parsed():
    report, session = _audit("lever-no-structured-field.json", "lever", "paper-kite")
    job = report["jobs"][0]
    assert job["observation"] == "explicit_empty"
    assert job["reason"] == "field_omitted"
    assert job["structured_range"] == "absent"
    assert job["ranges"] == []
    assert job["summary"] is None
    blob = json.dumps(job)
    assert "DESC-SENTINEL-190000" not in blob
    assert "HTML-SENTINEL-180000" not in blob
    assert report["coverage"]["ratio"] == "0/1"
    assert report["coverage"]["percent"] == 0
    assert report_has_errors(report) is False
    assert session.calls == ["https://api.lever.co/v0/postings/paper-kite?mode=json"]
    eu, eu_session = _audit("lever-no-structured-field.json", "lever", "paper-kite", region="eu")
    assert eu_session.calls == ["https://api.eu.lever.co/v0/postings/paper-kite?mode=json"]
    assert eu["jobs"][0]["structured_range"] == "absent"


def test_lever_null_empty_object_and_interval_variants():
    omitted = classify_lever_posting(
        {"descriptionPlain": "DESC-SENTINEL-190000", "salaryDescription": "<p>HTML-SENTINEL-180000</p>"}
    )
    assert omitted["reason"] == "field_omitted"
    assert "DESC-SENTINEL" not in json.dumps(omitted)
    assert classify_lever_posting({"salaryRange": None})["reason"] == "null"
    assert classify_lever_posting({"salaryRange": {}})["reason"] == "empty_object"
    symbolic = classify_lever_posting({"salaryRange": {"min": "$100,000", "max": "$120,000", "currency": "USD"}})
    assert symbolic["observation"] == "explicit_empty"
    assert symbolic["ranges"] == []
    hourly = classify_lever_posting(
        {
            "salaryRange": {"min": "35.5", "max": None, "currency": "gbp", "interval": "per-hour-wage"},
            "salaryDescriptionPlain": "official plain summary",
            "description": "ignore DESC-SENTINEL-999999",
        }
    )
    assert hourly["observation"] == "valid"
    assert hourly["ranges"][0]["min"] == "35.5"
    assert hourly["ranges"][0]["currency"] == "GBP"
    assert hourly["ranges"][0]["period"] == "per-hour-wage"
    assert hourly["summary"] == "official plain summary"
    assert "DESC-SENTINEL-999999" not in json.dumps(hourly)
    assert classify_lever_posting({"salaryRange": "70000"})["reason"] == "schema_incompatible"


def test_ashby_tier_bounds_win_over_summary_components_and_summary_text():
    payload = {
        "scrapeableCompensationSalarySummary": "SUMMARY-SENTINEL-81K",
        "compensationTiers": [
            {
                "title": "Zone B",
                "components": [
                    {
                        "compensationType": "Salary",
                        "interval": "1 YEAR",
                        "currencyCode": "USD",
                        "minValue": 200,
                        "maxValue": 300,
                    }
                ],
            },
            {
                "title": "Zone A",
                "components": [
                    {
                        "compensationType": "Salary",
                        "interval": "1 YEAR",
                        "currencyCode": "USD",
                        "minValue": 100,
                        "maxValue": 150,
                    }
                ],
            },
        ],
        "summaryComponents": [
            {
                "compensationType": "Salary",
                "interval": "1 YEAR",
                "currencyCode": "USD",
                "minValue": 1,
                "maxValue": 2,
            }
        ],
    }
    classified = classify_ashby_compensation(payload)
    assert [item["min"] for item in classified["ranges"]] == [100, 200]
    assert classified["summary"] == "SUMMARY-SENTINEL-81K"
    fallback = classify_ashby_compensation(
        {
            "summaryComponents": [
                {
                    "compensationType": "Salary",
                    "interval": "1 MONTH",
                    "currencyCode": "USD",
                    "minValue": 3000,
                    "maxValue": 4000,
                }
            ]
        }
    )
    assert fallback["ranges"][0]["source"] == "summary_components"
    assert fallback["ranges"][0]["period"] == "1 MONTH"
    assert classify_ashby_job({"title": "No key"})["observation"] == "unknown"


def test_diff_reports_bounds_adds_and_removals_without_treating_unknown_as_a_pay_edit():
    old = load_snapshot(FIXTURES / "diff-range-changed" / "old.json")
    new = load_snapshot(FIXTURES / "diff-range-changed" / "new.json")
    diff = diff_snapshots(old, new)
    assert [row["before"]["job_id"] for row in diff["bounds_changed"]] == ["job-a"]
    assert diff["bounds_changed"][0]["before"]["ranges"][0]["max"] == 90000
    assert diff["bounds_changed"][0]["after"]["ranges"][0]["max"] == 95000
    assert [row["job_id"] for row in diff["jobs_added"]] == ["job-c"]
    assert [row["job_id"] for row in diff["jobs_removed"]] == ["job-b"]
    assert [row["before"]["job_id"] for row in diff["became_valid"]] == ["job-d"]
    assert [row["before"]["job_id"] for row in diff["became_empty"]] == ["job-e"]
    assert [row["before"]["job_id"] for row in diff["unresolved"]] == ["job-f"]
    assert [row["before"]["job_id"] for row in diff["newly_observed"]] == ["job-g"]
    assert [row["before"]["job_id"] for row in diff["presentation_changed"]] == ["job-h"]
    assert diff["unchanged_count"] == 0

    same = json.loads(json.dumps(old))
    same["jobs"][1]["ranges"][0]["min"] = 80000.0
    assert diff_snapshots(old, same)["bounds_changed"] == []


def test_diff_currency_or_period_change_is_a_bounds_change():
    base = {
        "provider": "lever",
        "board": "paper-kite",
        "job_id": "p1",
        "title": "Role",
        "observation": "valid",
        "reason": "salary_bounds",
        "structured_range": "present",
        "ranges": [{"min": 10, "max": 20, "currency": "USD", "period": "per-year-salary"}],
        "summary": None,
        "error": None,
    }
    other = json.loads(json.dumps(base))
    other["ranges"][0]["currency"] = "EUR"
    wrapped = {"schema_version": 1, "tool": "ats-pay-range-audit", "jobs": [base]}
    changed = {"schema_version": 1, "tool": "ats-pay-range-audit", "jobs": [other]}
    assert len(diff_snapshots(wrapped, changed)["bounds_changed"]) == 1
    other["ranges"][0]["currency"] = "USD"
    other["ranges"][0]["period"] = "per-hour-wage"
    changed = {"schema_version": 1, "tool": "ats-pay-range-audit", "jobs": [other]}
    assert len(diff_snapshots(wrapped, changed)["bounds_changed"]) == 1


def test_schema_incompatible_board_is_an_error_without_invented_jobs():
    report, _session = _audit("schema-incompatible.json", "ashby", "hearth-and-quill")
    assert report["boards"][0]["ok"] is False
    assert report["boards"][0]["reason"] == "schema_incompatible"
    assert report["jobs"] == []
    assert report["coverage"]["ratio"] is None
    assert report["coverage"]["percent"] is None
    assert report["coverage"]["error"] == 1
    assert report_has_errors(report) is True


def test_duplicate_job_id_fails_the_board(tmp_path: Path):
    fixture = tmp_path / "dup.json"
    fixture.write_text(
        json.dumps(
            {
                "fictional": True,
                "provider": "ashby",
                "body": {
                    "jobs": [
                        {"id": "dup", "title": "One", "compensation": {}},
                        {"id": "dup", "title": "Two", "compensation": {}},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    report, _session = _audit_path(fixture, "ashby", "hearth-and-quill")
    assert report["jobs"] == []
    assert report["boards"][0]["reason"] == "duplicate_job_id"
    assert report["coverage"]["explicit_empty"] == 0


def test_snapshot_schema_errors(tmp_path: Path):
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"schema_version": 2, "jobs": []}', encoding="utf-8")
    with pytest.raises(FetchError) as caught:
        load_snapshot(wrong)
    assert caught.value.reason == "schema_incompatible"
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(FetchError) as caught:
        load_snapshot(bad)
    assert caught.value.reason == "parse_error"
    missing = tmp_path / "missing.json"
    with pytest.raises(UsageError):
        load_snapshot(missing)


def _audit_path(path: Path, provider: str, board: str):
    raw = FixtureRaw(path, provider)
    session = PoliteSession(raw, sleeper=lambda _seconds: None, clock=lambda: 0.0, pace=False)
    spec = Board(provider, board, "Fictional", "global", path)
    report = run_audit(
        [spec],
        lambda _board: session,
        generated_at="2026-11-11T00:00:00Z",
        max_details=500,
        network=False,
    )
    return report, session


def test_429_is_an_error_and_retry_after_is_honored():
    report, session = _audit("http-429.json", "ashby", "hearth-and-quill")
    assert report["jobs"] == []
    assert report["boards"][0]["reason"] == "http_429"
    assert report["coverage"]["explicit_empty"] == 0
    assert report["coverage"]["ratio"] is None
    assert report["coverage"]["percent"] is None
    assert len(session.calls) == 4

    clock = Clock()
    raw = ScriptRaw(
        [
            RawResponse(429, {"retry-after": "2"}, b"{}"),
            RawResponse(200, {}, b'{"jobs": []}'),
        ]
    )
    polite = PoliteSession(raw, sleeper=clock.sleep, clock=clock.clock, pace=False)
    body = polite.get_json(ashby_board_url("hearth-and-quill"), "ashby")
    assert body == {"jobs": []}
    assert clock.sleeps == [2.0]
    assert len(raw.calls) == 2

    clock = Clock()

    class AlwaysLimited:
        def __init__(self):
            self.calls: list[str] = []

        def get(self, url: str, timeout: float | None = None) -> RawResponse:
            self.calls.append(url)
            return RawResponse(429, {}, b"{}")

    raw = AlwaysLimited()
    polite = PoliteSession(raw, sleeper=clock.sleep, clock=clock.clock, pace=False)
    with pytest.raises(FetchError) as caught:
        polite.get_json(ashby_board_url("hearth-and-quill"), "ashby")
    assert caught.value.reason == "http_429"
    assert clock.sleeps == [1.0, 2.0, 4.0]
    assert len(raw.calls) == 4


def test_non_429_is_not_retried_and_redirects_are_not_followed():
    raw = ScriptRaw(
        [
            RawResponse(500, {}, b'{"error":"no"}'),
            RawResponse(200, {}, b"[]"),
        ]
    )
    polite = PoliteSession(raw, sleeper=lambda _seconds: None, clock=lambda: 0.0, pace=False)
    with pytest.raises(FetchError) as caught:
        polite.get_json(lever_board_url("paper-kite", "global"), "lever")
    assert caught.value.reason == "http_error"
    assert len(raw.calls) == 1

    raw = ScriptRaw([RawResponse(302, {"location": "http://169.254.169.254/"}, b"")])
    polite = PoliteSession(raw, sleeper=lambda _seconds: None, clock=lambda: 0.0, pace=False)
    with pytest.raises(FetchError) as caught:
        polite.get_json(greenhouse_list_url("ab"), "greenhouse")
    assert caught.value.reason == "redirect_blocked"
    assert raw.calls == [greenhouse_list_url("ab")]

    with pytest.raises(FetchError) as caught:
        _RejectRedirects().redirect_request(None, None, 302, "found", {}, "http://169.254.169.254/")
    assert caught.value.reason == "redirect_blocked"


def test_pace_floors_and_body_limit():
    assert resolved_intervals(None) == {"greenhouse": 0.5, "ashby": 0.5, "lever": 1.0}
    assert resolved_intervals(0.1)["lever"] == 1.0
    assert resolved_intervals(0.1)["greenhouse"] == 0.5
    assert resolved_intervals(2)["ashby"] == 2.0
    with pytest.raises(UsageError):
        resolved_intervals(-1)

    clock = Clock()
    raw = ScriptRaw(
        [
            RawResponse(200, {}, b"[]"),
            RawResponse(200, {}, b"[]"),
        ]
    )
    polite = PoliteSession(raw, sleeper=clock.sleep, clock=clock.clock, pace=True)
    polite.get_json(lever_board_url("paper-kite", "global"), "lever")
    polite.get_json(lever_board_url("paper-kite", "eu"), "lever")
    assert clock.sleeps == [1.0]

    class Big:
        def read(self, size: int) -> bytes:
            return b"x" * size

    with pytest.raises(FetchError) as caught:
        _read_response(200, {}, Big())
    assert caught.value.reason == "parse_error"
    assert MAX_BODY_BYTES == 8 * 1024 * 1024


def test_live_request_is_get_and_has_no_authorization(monkeypatch):
    seen = {}

    def fake_open(self, request, timeout=None):
        seen["method"] = request.get_method()
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        raise urllib.error.URLError("stop")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    with pytest.raises(FetchError):
        LiveRaw(5).get(greenhouse_list_url("ab"))
    assert seen["method"] == "GET"
    assert seen["authorization"] is None
    assert seen["url"] == greenhouse_list_url("ab")
    assert "pay_transparency" not in seen["url"]


def test_slugs_and_url_keys_are_rejected(tmp_path: Path):
    boards = tmp_path / "boards.yaml"
    boards.write_text(
        "boards:\n  - provider: greenhouse\n    board: ../evil\n",
        encoding="utf-8",
    )
    with pytest.raises(UsageError):
        load_boards(boards)
    boards.write_text(
        "boards:\n  - provider: ashby\n    board: ok\n    url: https://evil.example/job\n",
        encoding="utf-8",
    )
    with pytest.raises(UsageError):
        load_boards(boards)
    boards.write_text(
        "boards:\n  - provider: lever\n    board: paper-kite\n    region: http://169.254.169.254\n",
        encoding="utf-8",
    )
    with pytest.raises(UsageError):
        load_boards(boards)


def test_atomic_write_replaces_and_keeps_the_original_on_failure(tmp_path: Path, monkeypatch):
    target = tmp_path / "snap.json"
    target.write_text('{"keep": true}\n', encoding="utf-8")
    atomic_write_text(target, '{"schema_version": 1}\n')
    assert json.loads(target.read_text(encoding="utf-8")) == {"schema_version": 1}
    assert list(tmp_path.glob("*.tmp")) == []

    target.write_text('{"keep": true}\n', encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("disk")

    monkeypatch.setattr("ats_pay_range_audit.snapshot.os.replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(target, '{"schema_version": 2}\n')
    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": True}
    assert [path.name for path in tmp_path.iterdir()] == ["snap.json"]

    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(UsageError):
        atomic_write_text(link, "{}\n")
    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": True}


def test_cli_exit_codes_and_fixture_commands(capsys, monkeypatch, tmp_path: Path):
    def boom(*_args, **_kwargs):
        raise AssertionError("network was used")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", boom)

    code, _out, err = _cli([], capsys)
    assert code == 2
    assert "boards file" in err

    code, _out, err = _cli([str(ROOT / "missing.yaml")], capsys)
    assert code == 2
    assert "not found" in err

    code, out, _err = _cli(["--version"], capsys)
    assert code == 0
    assert out.strip() == __version__

    code, out, _err = _cli([str(EXAMPLES / "ashby-all-ranges.yaml"), "--json"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["coverage"]["percent"] == 100
    assert payload["coverage"]["explanation"]
    assert payload["network"] is False

    code, out, _err = _cli([str(EXAMPLES / "greenhouse-key-present-empty.yaml"), "--json"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["coverage"]["ratio"] == "0/2"
    assert all(job["observation"] == "explicit_empty" for job in payload["jobs"])
    assert "42424200" not in out

    code, out, _err = _cli([str(EXAMPLES / "lever-no-structured-field.yaml"), "--json"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["jobs"][0]["structured_range"] == "absent"
    assert "DESC-SENTINEL-190000" not in out

    code, out, _err = _cli([str(EXAMPLES / "http-429.yaml"), "--json"], capsys)
    assert code == 1
    payload = json.loads(out)
    assert payload["jobs"] == []
    assert payload["boards"][0]["reason"] == "http_429"
    assert payload["coverage"]["percent"] is None
    assert payload["coverage"]["explicit_empty"] == 0

    code, out, _err = _cli([str(EXAMPLES / "schema-incompatible.yaml"), "--json"], capsys)
    assert code == 1
    assert json.loads(out)["boards"][0]["reason"] == "schema_incompatible"

    code, out, _err = _cli(
        [
            "--diff",
            str(FIXTURES / "diff-range-changed" / "old.json"),
            str(FIXTURES / "diff-range-changed" / "new.json"),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    diff = json.loads(out)
    assert diff["bounds_changed"][0]["after"]["ranges"][0]["max"] == 95000
    assert diff["jobs_added"][0]["job_id"] == "job-c"
    assert diff["jobs_removed"][0]["job_id"] == "job-b"

    code, _out, err = _cli(["--diff", str(FIXTURES / "missing.json"), str(FIXTURES / "missing.json")], capsys)
    assert code == 2
    assert "not found" in err

    wrong = tmp_path / "schema-2.json"
    wrong.write_text('{"schema_version": 2, "jobs": []}\n', encoding="utf-8")
    code, _out, err = _cli(["--diff", str(wrong), str(wrong)], capsys)
    assert code == 1
    assert "schema_version" in err


def test_cli_save_is_the_json_report_and_refuses_a_symlink(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr(
        urllib.request.OpenerDirector,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    target = tmp_path / "snap.json"
    code, out, _err = _cli(
        [str(EXAMPLES / "ashby-all-ranges.yaml"), "--json", "--save", str(target)],
        capsys,
    )
    assert code == 0
    assert target.read_text(encoding="utf-8") == out
    assert json.loads(out)["coverage"]["percent"] == 100

    human = tmp_path / "human.json"
    code, out, _err = _cli(
        [str(EXAMPLES / "lever-no-structured-field.yaml"), "--save", str(human)],
        capsys,
    )
    assert code == 0
    assert "structured_range=absent" in out
    assert "unknown is excluded" in out
    saved = json.loads(human.read_text(encoding="utf-8"))
    assert saved["jobs"][0]["structured_range"] == "absent"

    link = tmp_path / "link.json"
    link.symlink_to(target)
    code, _out, err = _cli(
        [str(EXAMPLES / "ashby-all-ranges.yaml"), "--save", str(link)],
        capsys,
    )
    assert code == 2
    assert "symlink" in err


def test_cli_refuses_network_without_live_and_rejects_bad_flags(tmp_path: Path, capsys):
    boards = tmp_path / "live.yaml"
    boards.write_text(
        "boards:\n  - provider: ashby\n    board: hearth-and-quill\n    name: Hearth\n",
        encoding="utf-8",
    )
    code, _out, err = _cli([str(boards)], capsys)
    assert code == 2
    assert "--live" in err
    code, _out, err = _cli([str(boards), "--max-details", "10001"], capsys)
    assert code == 2
    code, _out, err = _cli([str(EXAMPLES / "ashby-all-ranges.yaml"), "--min-interval", "-1"], capsys)
    assert code == 2
    code, _out, err = _cli(
        [str(EXAMPLES / "ashby-all-ranges.yaml"), "--diff", "a.json", "b.json"],
        capsys,
    )
    assert code == 2


def test_fixture_audit_does_not_open_a_socket(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", boom)
    report, _session = _audit("ashby-all-ranges.json", "ashby", "hearth-and-quill")
    assert report["network"] is False


def test_multi_board_keeps_successes_when_one_board_fails(tmp_path: Path):
    boards = tmp_path / "mix.yaml"
    boards.write_text(
        "\n".join(
            [
                "boards:",
                "  - provider: greenhouse",
                "    board: northwind-fictional",
                "    name: Northwind Lantern (fictional)",
                f"    fixture: {FIXTURES / 'greenhouse-key-present-empty.json'}",
                "  - provider: ashby",
                "    board: hearth-and-quill",
                "    name: \"Hearth & Quill (fictional)\"",
                f"    fixture: {FIXTURES / 'http-429.json'}",
            ]
        ),
        encoding="utf-8",
    )
    loaded = load_boards(boards)
    sessions = {}

    def session_for(board: Board):
        raw = FixtureRaw(board.fixture, board.provider)
        session = PoliteSession(raw, sleeper=lambda _seconds: None, clock=lambda: 0.0, pace=False)
        sessions[board.provider] = session
        return session

    report = run_audit(
        loaded,
        session_for,
        generated_at="2026-11-11T00:00:00Z",
        max_details=500,
        network=False,
    )
    assert report_has_errors(report) is True
    assert [job["provider"] for job in report["jobs"]] == ["greenhouse", "greenhouse"]
    assert report["boards"][1]["reason"] == "http_429"
    assert report["coverage"]["explicit_empty"] == 2
    assert report["coverage"]["error"] == 1


def test_max_details_zero_does_not_invent_empty_pay(monkeypatch):
    monkeypatch.setattr(
        urllib.request.OpenerDirector,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    report, session = _audit(
        "greenhouse-list-must-not-decide.json",
        "greenhouse",
        "northwind-fictional",
        max_details=0,
    )
    assert session.calls == [greenhouse_list_url("northwind-fictional")]
    assert {job["reason"] for job in report["jobs"]} == {"detail_budget_exhausted"}
    assert report["coverage"]["ratio"] is None
    assert report["coverage"]["unknown"] == 3
    assert "43434301" not in json.dumps(report)


def test_greenhouse_job_level_429_does_not_blank_the_sibling(tmp_path: Path):
    fixture = tmp_path / "one-429.json"
    fixture.write_text(
        json.dumps(
            {
                "fictional": True,
                "provider": "greenhouse",
                "list": {
                    "jobs": [
                        {"id": 1, "title": "Kept"},
                        {"id": 2, "title": "Limited"},
                    ]
                },
                "details": {
                    "1": {"id": 1, "title": "Kept", "pay_input_ranges": []},
                    "2": {
                        "status": 429,
                        "headers": {"Retry-After": "0"},
                        "body": {"error": "slow"},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    report, session = _audit_path(fixture, "greenhouse", "northwind-fictional")
    by_id = {job["job_id"]: job for job in report["jobs"]}
    assert by_id["1"]["observation"] == "explicit_empty"
    assert by_id["2"]["observation"] == "error"
    assert by_id["2"]["reason"] == "http_429"
    assert by_id["2"]["ranges"] == []
    assert report["coverage"]["denominator"] == 1
    assert report["coverage"]["ratio"] == "0/1"
    assert sum(1 for url in session.calls if url.endswith("/jobs/2?pay_transparency=true")) == 4
    assert all("pay_input_ranges=" not in url for url in session.calls)


def test_off_host_display_urls_are_dropped(tmp_path: Path):
    fixture = tmp_path / "lever.json"
    fixture.write_text(
        json.dumps(
            {
                "fictional": True,
                "provider": "lever",
                "body": [
                    {
                        "id": "post-1",
                        "text": "Role",
                        "hostedUrl": "https://evil.example/post-1",
                        "description": "DESC-SENTINEL-190000",
                        "salaryRange": {"min": 10, "max": 12, "currency": "USD", "interval": "year"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report, _session = _audit_path(fixture, "lever", "paper-kite")
    assert report["jobs"][0]["url"] is None
    assert report["jobs"][0]["ranges"][0]["min"] == 10
    blob = json.dumps(report)
    assert "evil.example" not in blob
    assert "DESC-SENTINEL-190000" not in blob


def test_documented_urls_and_slug_rejection():
    zero = classify_lever_posting({"salaryRange": {"min": 0, "max": 0, "currency": "USD", "interval": "year"}})
    assert zero["observation"] == "valid"
    assert zero["ranges"][0]["min"] == 0
    assert zero["ranges"][0]["max"] == 0
    assert classify_ashby_compensation({"compensationTiers": []})["reason"] == "empty_tiers"
    assert greenhouse_detail_url("ab", "15") == (
        "https://boards-api.greenhouse.io/v1/boards/ab/jobs/15?pay_transparency=true"
    )
    assert greenhouse_list_url("ab") == "https://boards-api.greenhouse.io/v1/boards/ab/jobs"
    with pytest.raises(UsageError):
        greenhouse_list_url("https://evil.example")
    with pytest.raises(UsageError):
        lever_board_url("paper-kite", "evil")
    assert "pay_input_ranges=" not in greenhouse_detail_url("ab", "15")


def test_bonus_and_commission_are_not_a_salary_range():
    only = classify_ashby_compensation(
        {
            "compensationTiers": [
                {
                    "title": "Paper zone",
                    "components": [
                        {
                            "compensationType": "Bonus",
                            "interval": "1 YEAR",
                            "currencyCode": "USD",
                            "minValue": 5000,
                            "maxValue": 8000,
                            "summary": "bonus only",
                        },
                        {
                            "compensationType": "Commission",
                            "interval": "1 YEAR",
                            "currencyCode": "USD",
                            "minValue": 10000,
                            "maxValue": 20000,
                            "summary": "commission only",
                        },
                    ],
                }
            ]
        }
    )
    assert only["observation"] == "explicit_empty"
    assert only["reason"] == "no_salary_component"
    assert only["ranges"] == []
    mixed = classify_ashby_compensation(
        {
            "compensationTiers": [
                {
                    "title": "Zone",
                    "components": [
                        {
                            "compensationType": "Commission",
                            "interval": "1 YEAR",
                            "currencyCode": "USD",
                            "minValue": 111,
                            "maxValue": 222,
                        },
                        {
                            "compensationType": "Salary",
                            "interval": "1 YEAR",
                            "currencyCode": "USD",
                            "minValue": 40000,
                            "maxValue": 50000,
                        },
                        {
                            "compensationType": "Bonus",
                            "interval": "1 YEAR",
                            "currencyCode": "USD",
                            "minValue": 333,
                            "maxValue": 444,
                        },
                    ],
                }
            ]
        }
    )
    assert mixed["observation"] == "valid"
    assert [item["min"] for item in mixed["ranges"]] == [40000]
    blob = json.dumps(mixed["ranges"])
    assert "111" not in blob
    assert "333" not in blob


def test_timeout_stays_outside_the_denominator(monkeypatch):
    class TimeoutRaw:
        def get(self, url: str, timeout: float | None = None) -> RawResponse:
            raise TimeoutError("timed out")

    session = PoliteSession(TimeoutRaw(), sleeper=lambda _seconds: None, clock=lambda: 0.0, pace=False)
    spec = Board("ashby", "hearth-and-quill", "Hearth & Quill (fictional)", "global", None)
    report = run_audit(
        [spec],
        lambda _board: session,
        generated_at="2026-11-11T00:00:00Z",
        max_details=5,
        network=False,
    )
    assert report["boards"][0]["reason"] == "timeout"
    assert report["jobs"] == []
    assert report["coverage"]["explicit_empty"] == 0
    assert report["coverage"]["error"] == 1
    assert report["coverage"]["ratio"] is None
    assert report["coverage"]["percent"] is None

    class ListThenTimeout:
        def get(self, url: str, timeout: float | None = None) -> RawResponse:
            if url.endswith("/jobs"):
                body = json.dumps(
                    {"jobs": [{"id": 1, "title": "Kept"}, {"id": 2, "title": "Slow"}]}
                ).encode()
                return RawResponse(200, {}, body)
            if "/jobs/1?" in url:
                body = json.dumps({"id": 1, "title": "Kept", "pay_input_ranges": []}).encode()
                return RawResponse(200, {}, body)
            raise TimeoutError("timed out")

    session = PoliteSession(ListThenTimeout(), sleeper=lambda _seconds: None, clock=lambda: 0.0, pace=False)
    spec = Board("greenhouse", "northwind-fictional", "Northwind Lantern (fictional)", "global", None)
    report = run_audit(
        [spec],
        lambda _board: session,
        generated_at="2026-11-11T00:00:00Z",
        max_details=5,
        network=False,
    )
    by_id = {job["job_id"]: job for job in report["jobs"]}
    assert by_id["1"]["observation"] == "explicit_empty"
    assert by_id["2"]["observation"] == "error"
    assert by_id["2"]["reason"] == "timeout"
    assert by_id["2"]["ranges"] == []
    assert report["coverage"]["denominator"] == 1
    assert report["coverage"]["ratio"] == "0/1"
    assert report["coverage"]["error"] == 1

    def fake_open(self, request, timeout=None):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    with pytest.raises(FetchError) as caught:
        LiveRaw(5).get(greenhouse_list_url("ab"))
    assert caught.value.reason == "timeout"


def test_write_examples_is_a_wheel_entry_and_runs_offline(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr(
        urllib.request.OpenerDirector,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    dest = tmp_path / "exported"
    code, out, err = _cli(["--write-examples", str(dest)], capsys)
    assert code == 0
    assert err == ""
    assert "ashby-all-ranges.yaml" in out
    copied = json.loads((dest / "fixtures" / "ashby-all-ranges.json").read_text(encoding="utf-8"))
    assert copied["fictional"] is True
    code, out, _err = _cli([str(dest / "examples" / "ashby-all-ranges.yaml"), "--json"], capsys)
    assert code == 0
    assert json.loads(out)["coverage"]["ratio"] == "2/2"
    code, _out, err = _cli(["--write-examples", str(dest)], capsys)
    assert code == 2
    assert "existing path" in err
