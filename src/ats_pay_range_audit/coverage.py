"""Coverage math. Unknown and errors stay outside the denominator."""

from __future__ import annotations

from ats_pay_range_audit.constants import (
    DENOMINATOR_EXPLANATION,
    OBSERVATION_ERROR,
    OBSERVATION_EXPLICIT_EMPTY,
    OBSERVATION_UNKNOWN,
    OBSERVATION_VALID,
)


def coverage_block(jobs: list[dict], board_errors: int) -> dict:
    counts = {
        OBSERVATION_VALID: 0,
        OBSERVATION_EXPLICIT_EMPTY: 0,
        OBSERVATION_UNKNOWN: 0,
        OBSERVATION_ERROR: 0,
    }
    for job in jobs:
        observation = job["observation"]
        counts[observation] = counts.get(observation, 0) + 1
    numerator = counts[OBSERVATION_VALID]
    denominator = counts[OBSERVATION_VALID] + counts[OBSERVATION_EXPLICIT_EMPTY]
    return {
        "valid": numerator,
        "explicit_empty": counts[OBSERVATION_EXPLICIT_EMPTY],
        "unknown": counts[OBSERVATION_UNKNOWN],
        "job_errors": counts[OBSERVATION_ERROR],
        "board_errors": board_errors,
        "error": counts[OBSERVATION_ERROR] + board_errors,
        "jobs": len(jobs),
        "numerator": numerator,
        "denominator": denominator,
        "ratio": None if denominator == 0 else f"{numerator}/{denominator}",
        "percent": None if denominator == 0 else _percent(numerator, denominator),
        "unknown_is_not_no_pay": True,
        "empty_compensation_is_not_valid": True,
        "explanation": DENOMINATOR_EXPLANATION,
    }


def _percent(numerator: int, denominator: int) -> float:
    scaled = (numerator * 10000 + denominator // 2) // denominator
    whole = scaled // 100
    fraction = scaled % 100
    if fraction == 0:
        return float(whole)
    return whole + fraction / 100
