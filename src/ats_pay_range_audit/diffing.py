"""Compare two snapshots. Unknown and error are not reported as a pay-range edit."""

from __future__ import annotations

from ats_pay_range_audit.constants import (
    OBSERVATION_ERROR,
    OBSERVATION_EXPLICIT_EMPTY,
    OBSERVATION_UNKNOWN,
    OBSERVATION_VALID,
    SCHEMA_VERSION,
    TOOL_NAME,
)
from ats_pay_range_audit.money import canon_amount

_UNRESOLVED = {OBSERVATION_UNKNOWN, OBSERVATION_ERROR}


def diff_snapshots(old: dict, new: dict) -> dict:
    old_index = _index(old)
    new_index = _index(new)
    old_keys = set(old_index)
    new_keys = set(new_index)

    jobs_added = [_public(new_index[key]) for key in sorted(new_keys - old_keys)]
    jobs_removed = [_public(old_index[key]) for key in sorted(old_keys - new_keys)]
    bounds_changed = []
    became_valid = []
    became_empty = []
    newly_observed = []
    unresolved = []
    presentation_changed = []
    title_changed = []
    unchanged = 0

    for key in sorted(old_keys & new_keys):
        before = old_index[key]
        after = new_index[key]
        title_differs = (before.get("title") or "") != (after.get("title") or "")
        if title_differs:
            title_changed.append(_pair(before, after))
        before_obs = before["observation"]
        after_obs = after["observation"]
        if before_obs in _UNRESOLVED or after_obs in _UNRESOLVED:
            if before_obs in _UNRESOLVED and after_obs == OBSERVATION_VALID:
                newly_observed.append(_pair(before, after))
            else:
                unresolved.append(_pair(before, after))
            continue
        if before_obs == OBSERVATION_VALID and after_obs == OBSERVATION_VALID:
            if _bounds(before) != _bounds(after):
                bounds_changed.append(_pair(before, after))
            elif _presentation(before) != _presentation(after):
                presentation_changed.append(_pair(before, after))
            elif not title_differs:
                unchanged += 1
            continue
        if before_obs == OBSERVATION_EXPLICIT_EMPTY and after_obs == OBSERVATION_VALID:
            became_valid.append(_pair(before, after))
            continue
        if before_obs == OBSERVATION_VALID and after_obs == OBSERVATION_EXPLICIT_EMPTY:
            became_empty.append(_pair(before, after))
            continue
        if not title_differs:
            unchanged += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "kind": "diff",
        "bounds_changed": bounds_changed,
        "became_valid": became_valid,
        "became_empty": became_empty,
        "newly_observed": newly_observed,
        "jobs_added": jobs_added,
        "jobs_removed": jobs_removed,
        "unresolved": unresolved,
        "presentation_changed": presentation_changed,
        "title_changed": title_changed,
        "unchanged_count": unchanged,
        "note": (
            "bounds_changed means min, max, currency, or period changed on a job that was valid "
            "in both snapshots. A move from unknown or error is unresolved or newly_observed, "
            "not a claim that the employer added or removed a range. Jobs are sorted by "
            "provider, board, and job id."
        ),
    }


def _index(snapshot: dict) -> dict[tuple[str, str, str], dict]:
    index = {}
    for job in snapshot["jobs"]:
        key = (str(job["provider"]), str(job["board"]), str(job["job_id"]))
        index[key] = job
    return index


def _bounds(job: dict) -> tuple:
    items = []
    for item in job.get("ranges") or []:
        if not isinstance(item, dict):
            continue
        items.append(
            (
                item.get("currency"),
                item.get("period"),
                canon_amount(item.get("min")),
                canon_amount(item.get("max")),
            )
        )
    return tuple(sorted(items, key=lambda row: tuple("" if part is None else str(part) for part in row)))


def _presentation(job: dict) -> tuple:
    items = []
    for item in job.get("ranges") or []:
        if not isinstance(item, dict):
            continue
        items.append((item.get("label") or "", item.get("summary") or ""))
    return (job.get("summary") or "", tuple(sorted(items)))


def _public(job: dict) -> dict:
    return {
        "provider": job.get("provider"),
        "board": job.get("board"),
        "company": job.get("company"),
        "job_id": job.get("job_id"),
        "title": job.get("title"),
        "observation": job.get("observation"),
        "reason": job.get("reason"),
        "structured_range": job.get("structured_range"),
        "summary": job.get("summary"),
        "ranges": job.get("ranges") or [],
        "error": job.get("error"),
    }


def _pair(before: dict, after: dict) -> dict:
    return {"before": _public(before), "after": _public(after)}
