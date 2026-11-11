"""Walk the documented GETs and classify each job."""

from __future__ import annotations

import re

from ats_pay_range_audit import __version__
from ats_pay_range_audit.boards import Board
from ats_pay_range_audit.classify import (
    classification,
    classify_ashby_job,
    classify_greenhouse_detail,
    classify_lever_posting,
)
from ats_pay_range_audit.constants import (
    LAUNCH_WINDOW_END,
    METHODOLOGY,
    OBSERVATION_ERROR,
    OBSERVATION_UNKNOWN,
    REASON_DETAIL_BUDGET_EXHAUSTED,
    REASON_DUPLICATE_JOB_ID,
    REASON_MISSING_JOB_IDENTITY,
    REASON_SCHEMA_INCOMPATIBLE,
    SCHEMA_VERSION,
    SELECTED_DATE,
    TOOL_NAME,
)
from ats_pay_range_audit.coverage import coverage_block
from ats_pay_range_audit.errors import FetchError
from ats_pay_range_audit.money import short_text
from ats_pay_range_audit.urls import (
    GREENHOUSE_JOB_ID,
    ashby_board_url,
    greenhouse_canonical_job_url,
    greenhouse_detail_url,
    greenhouse_list_url,
    lever_board_url,
    public_https_url,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")


def run_audit(boards: list[Board], session_for, *, generated_at: str, max_details: int, network: bool) -> dict:
    board_rows = []
    jobs: list[dict] = []
    for board in boards:
        session = session_for(board)
        row, found = audit_board(board, session, max_details=max_details)
        board_rows.append(row)
        jobs.extend(found)
    jobs.sort(key=_job_sort_key)
    board_errors = sum(1 for row in board_rows if not row["ok"])
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": __version__,
        "selected_date": SELECTED_DATE,
        "launch_window_end": LAUNCH_WINDOW_END,
        "generated_at": generated_at,
        "network": network,
        "legal": METHODOLOGY["legal"],
        "methodology": {
            "greenhouse": METHODOLOGY["greenhouse"],
            "ashby": METHODOLOGY["ashby"],
            "lever": METHODOLOGY["lever"],
            "coverage_denominator": METHODOLOGY["coverage_denominator"],
            "legal": METHODOLOGY["legal"],
        },
        "coverage": coverage_block(jobs, board_errors),
        "boards": board_rows,
        "jobs": jobs,
    }


def audit_board(board: Board, session, *, max_details: int) -> tuple[dict, list[dict]]:
    notes: list[str] = []
    try:
        if board.provider == "greenhouse":
            jobs = _greenhouse(board, session, max_details, notes)
        elif board.provider == "ashby":
            jobs = _ashby(board, session, notes)
        elif board.provider == "lever":
            jobs = _lever(board, session, notes)
        else:
            raise FetchError("provider_unsupported", f"unsupported provider {board.provider}")
    except FetchError as exc:
        return _board_row(board, ok=False, reason=exc.reason, error=exc.message, notes=notes, count=0), []
    jobs.sort(key=_job_sort_key)
    return _board_row(board, ok=True, reason=None, error=None, notes=notes, count=len(jobs)), jobs


def report_has_errors(report: dict) -> bool:
    return bool(report["coverage"]["error"])


def _greenhouse(board: Board, session, max_details: int, notes: list[str]) -> list[dict]:
    payload = session.get_json(greenhouse_list_url(board.board), "greenhouse")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise FetchError(
            REASON_SCHEMA_INCOMPATIBLE,
            "Greenhouse list JSON did not contain a jobs array",
        )
    listed = payload["jobs"]
    if any(isinstance(item, dict) and "pay_input_ranges" in item for item in listed):
        notes.append("ignored_list_pay_fields")
    meta = payload.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("total"), int) and not isinstance(meta.get("total"), bool):
        if meta["total"] != len(listed):
            notes.append("list_count_mismatch")
    prepared = []
    invalid_rows = []
    seen: set[str] = set()
    for index, item in enumerate(listed):
        job_id = _greenhouse_id(item.get("id")) if isinstance(item, dict) else None
        if job_id is None:
            invalid_rows.append(index)
            continue
        if job_id in seen:
            raise FetchError(REASON_DUPLICATE_JOB_ID, f"Greenhouse list repeats job id {job_id}")
        seen.add(job_id)
        prepared.append(item)
    prepared.sort(key=lambda item: int(_greenhouse_id(item.get("id")) or "0"))
    if invalid_rows:
        notes.append(f"skipped_invalid_list_entries:{len(invalid_rows)}")
    if max_details < 0:
        chosen = prepared
        held = []
    else:
        chosen = prepared[:max_details]
        held = prepared[max_details:]
    if held:
        notes.append("detail_budget_exhausted")
    jobs = []
    for item in chosen:
        job_id = _greenhouse_id(item.get("id")) or ""
        title = short_text(item.get("title")) or "untitled"
        url = public_https_url(item.get("absolute_url"), "greenhouse") or greenhouse_canonical_job_url(
            board.board, job_id
        )
        try:
            detail = session.get_json(greenhouse_detail_url(board.board, job_id), "greenhouse")
        except FetchError as exc:
            jobs.append(_job(board, job_id, title, url, _error(exc.reason, exc.message)))
            continue
        if isinstance(detail, dict):
            detail_title = short_text(detail.get("title"))
            if detail_title:
                title = detail_title
            detail_url = public_https_url(detail.get("absolute_url"), "greenhouse")
            if detail_url:
                url = detail_url
        jobs.append(_job(board, job_id, title, url, classify_greenhouse_detail(detail)))
    for item in held:
        job_id = _greenhouse_id(item.get("id")) or ""
        title = short_text(item.get("title")) or "untitled"
        url = public_https_url(item.get("absolute_url"), "greenhouse") or greenhouse_canonical_job_url(
            board.board, job_id
        )
        jobs.append(
            _job(
                board,
                job_id,
                title,
                url,
                classification(OBSERVATION_UNKNOWN, REASON_DETAIL_BUDGET_EXHAUSTED),
            )
        )
    for index in invalid_rows:
        jobs.append(
            _job(
                board,
                f"invalid-list-entry-{index}",
                "untitled",
                None,
                _error(REASON_SCHEMA_INCOMPATIBLE, "Greenhouse list entry had no decimal job id"),
            )
        )
    return jobs


def _ashby(board: Board, session, notes: list[str]) -> list[dict]:
    payload = session.get_json(ashby_board_url(board.board), "ashby")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise FetchError(
            REASON_SCHEMA_INCOMPATIBLE,
            "Ashby JSON did not contain a jobs array",
        )
    if "compensation" in payload and not any(
        isinstance(job, dict) and "compensation" in job for job in payload["jobs"]
    ):
        notes.append("ignored_top_level_compensation")
    elif "compensation" in payload:
        notes.append("ignored_top_level_compensation")
    return _rows_from_objects(
        board,
        payload["jobs"],
        classify_ashby_job,
        _ashby_identity,
        "title",
        "jobUrl",
        "ashby",
    )


def _lever(board: Board, session, notes: list[str]) -> list[dict]:
    del notes
    payload = session.get_json(lever_board_url(board.board, board.region), "lever")
    if not isinstance(payload, list):
        raise FetchError(
            REASON_SCHEMA_INCOMPATIBLE,
            "Lever JSON mode did not return an array of postings",
        )
    return _rows_from_objects(
        board,
        payload,
        classify_lever_posting,
        _lever_identity,
        "text",
        "hostedUrl",
        "lever",
    )


def _rows_from_objects(board, items, classify, identify, title_key, url_key, provider) -> list[dict]:
    jobs = []
    seen: set[str] = set()
    missing = 0
    for item in items:
        if not isinstance(item, dict):
            missing += 1
            jobs.append(
                _job(
                    board,
                    f"missing-identity-{missing}",
                    "untitled",
                    None,
                    _error(REASON_SCHEMA_INCOMPATIBLE, f"{provider} posting was not an object"),
                )
            )
            continue
        job_id = identify(item)
        if job_id is None:
            missing += 1
            jobs.append(
                _job(
                    board,
                    f"missing-identity-{missing}",
                    short_text(item.get(title_key)) or "untitled",
                    None,
                    _error(REASON_MISSING_JOB_IDENTITY, f"{provider} posting had no safe public id"),
                )
            )
            continue
        if job_id in seen:
            raise FetchError(REASON_DUPLICATE_JOB_ID, f"{provider} payload repeats job id {job_id}")
        seen.add(job_id)
        url = public_https_url(item.get(url_key), provider)
        jobs.append(
            _job(
                board,
                job_id,
                short_text(item.get(title_key)) or "untitled",
                url,
                classify(item),
            )
        )
    return jobs


def _job(board: Board, job_id: str, title: str, url: str | None, classified: dict) -> dict:
    return {
        "provider": board.provider,
        "board": board.board,
        "company": board.name,
        "job_id": job_id,
        "title": title,
        "url": url,
        "observation": classified["observation"],
        "reason": classified["reason"],
        "structured_range": classified["structured_range"],
        "summary": classified["summary"],
        "ranges": classified["ranges"],
        "error": classified["error"],
    }


def _error(reason: str, message: str) -> dict:
    return classification(OBSERVATION_ERROR, reason, error=message)


def _board_row(board: Board, *, ok: bool, reason: str | None, error: str | None, notes: list[str], count: int) -> dict:
    return {
        "provider": board.provider,
        "board": board.board,
        "company": board.name,
        "region": board.region,
        "ok": ok,
        "reason": reason,
        "error": error,
        "notes": list(notes),
        "jobs_observed": count,
    }


def _greenhouse_id(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    if GREENHOUSE_JOB_ID.fullmatch(text) is None:
        return None
    return text


def _ashby_identity(job: dict) -> str | None:
    raw = job.get("id")
    if isinstance(raw, str) and _SAFE_ID.fullmatch(raw):
        return raw
    if isinstance(raw, int) and not isinstance(raw, bool):
        text = str(raw)
        if _SAFE_ID.fullmatch(text):
            return text
    url = public_https_url(job.get("jobUrl"), "ashby")
    if not url:
        return None
    segment = url.rstrip("/").rsplit("/", 1)[-1]
    if _SAFE_ID.fullmatch(segment):
        return segment
    return None


def _lever_identity(posting: dict) -> str | None:
    raw = posting.get("id")
    if isinstance(raw, str) and _SAFE_ID.fullmatch(raw):
        return raw
    return None


def _job_sort_key(job: dict) -> tuple:
    return (job["provider"], job["board"], job["job_id"], job["title"])
