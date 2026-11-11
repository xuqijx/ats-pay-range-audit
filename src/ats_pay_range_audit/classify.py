"""Turn one documented payload into an observation. No HTML and no salary regex."""

from __future__ import annotations

from ats_pay_range_audit.constants import (
    OBSERVATION_ERROR,
    OBSERVATION_EXPLICIT_EMPTY,
    OBSERVATION_UNKNOWN,
    OBSERVATION_VALID,
    REASON_EMPTY_ARRAY,
    REASON_EMPTY_OBJECT,
    REASON_EMPTY_TIERS,
    REASON_FIELD_NOT_IN_RESPONSE,
    REASON_FIELD_OMITTED,
    REASON_NO_NUMERIC_BOUNDS,
    REASON_NO_SALARY_COMPONENT,
    REASON_NULL,
    REASON_SALARY_BOUNDS,
    REASON_SCHEMA_INCOMPATIBLE,
    REASON_SUMMARY_ONLY,
    STRUCTURED_ABSENT,
    STRUCTURED_ERROR,
    STRUCTURED_PRESENT,
    STRUCTURED_UNKNOWN,
)
from ats_pay_range_audit.money import (
    amount,
    cents_to_major,
    currency_code,
    period_text,
    short_text,
    sort_ranges,
    whole_cents,
)


def structured_label(observation: str) -> str:
    return {
        OBSERVATION_VALID: STRUCTURED_PRESENT,
        OBSERVATION_EXPLICIT_EMPTY: STRUCTURED_ABSENT,
        OBSERVATION_UNKNOWN: STRUCTURED_UNKNOWN,
        OBSERVATION_ERROR: STRUCTURED_ERROR,
    }[observation]


def classification(
    observation: str,
    reason: str,
    ranges: list[dict] | None = None,
    summary: str | None = None,
    error: str | None = None,
) -> dict:
    return {
        "observation": observation,
        "reason": reason,
        "structured_range": structured_label(observation),
        "ranges": sort_ranges(list(ranges or [])),
        "summary": summary,
        "error": error,
    }


def classify_greenhouse_detail(payload: object) -> dict:
    """Classify a Retrieve-a-job body. List payloads must not be passed here."""

    if not isinstance(payload, dict):
        return classification(
            OBSERVATION_ERROR,
            REASON_SCHEMA_INCOMPATIBLE,
            error="Greenhouse detail body was not a JSON object",
        )
    if "pay_input_ranges" not in payload:
        return classification(OBSERVATION_UNKNOWN, REASON_FIELD_NOT_IN_RESPONSE)
    raw = payload["pay_input_ranges"]
    if raw is None:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_NULL)
    if isinstance(raw, dict):
        if len(raw) == 0:
            return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_EMPTY_OBJECT)
        return classification(
            OBSERVATION_ERROR,
            REASON_SCHEMA_INCOMPATIBLE,
            error="Greenhouse pay_input_ranges was an object, not an array",
        )
    if isinstance(raw, str):
        return classification(
            OBSERVATION_ERROR,
            REASON_SCHEMA_INCOMPATIBLE,
            error="Greenhouse pay_input_ranges was a string",
        )
    if not isinstance(raw, list):
        return classification(
            OBSERVATION_ERROR,
            REASON_SCHEMA_INCOMPATIBLE,
            error="Greenhouse pay_input_ranges had an unexpected type",
        )
    if len(raw) == 0:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_EMPTY_ARRAY)
    ranges: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        minimum = cents_to_major(whole_cents(item.get("min_cents")))
        maximum = cents_to_major(whole_cents(item.get("max_cents")))
        if minimum is None and maximum is None:
            continue
        ranges.append(
            {
                "min": minimum,
                "max": maximum,
                "currency": currency_code(item.get("currency_type")),
                "period": period_text(item.get("period")),
                "label": short_text(item.get("title")),
                "summary": None,
                "source": "pay_input_ranges",
            }
        )
    if not ranges:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_NO_NUMERIC_BOUNDS)
    return classification(OBSERVATION_VALID, REASON_SALARY_BOUNDS, ranges)


def classify_ashby_job(job: object) -> dict:
    if not isinstance(job, dict):
        return classification(
            OBSERVATION_ERROR,
            REASON_SCHEMA_INCOMPATIBLE,
            error="Ashby job was not a JSON object",
        )
    if "compensation" not in job:
        return classification(OBSERVATION_UNKNOWN, REASON_FIELD_NOT_IN_RESPONSE)
    return classify_ashby_compensation(job["compensation"])


def classify_ashby_compensation(raw: object) -> dict:
    if raw is None:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_NULL)
    if not isinstance(raw, dict):
        return classification(
            OBSERVATION_ERROR,
            REASON_SCHEMA_INCOMPATIBLE,
            error="Ashby compensation was not an object",
        )
    summary = _ashby_summary(raw)
    if len(raw) == 0:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_EMPTY_OBJECT, summary=summary)

    tier_components, saw_salary = _salary_from_tiers(raw.get("compensationTiers"))
    source = "compensation_tiers"
    components = tier_components
    if not saw_salary:
        components, saw_salary = _salary_from_summary_components(raw.get("summaryComponents"))
        source = "summary_components"

    ranges = []
    for label, component in components:
        built = _salary_component_range(component, label, source)
        if built is not None:
            ranges.append(built)
    if ranges:
        return classification(OBSERVATION_VALID, REASON_SALARY_BOUNDS, ranges, summary)
    if saw_salary:
        return classification(
            OBSERVATION_EXPLICIT_EMPTY,
            REASON_NO_NUMERIC_BOUNDS,
            summary=summary,
        )
    if _has_non_salary_component(raw):
        return classification(
            OBSERVATION_EXPLICIT_EMPTY,
            REASON_NO_SALARY_COMPONENT,
            summary=summary,
        )
    if summary:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_SUMMARY_ONLY, summary=summary)
    tiers = raw.get("compensationTiers")
    if isinstance(tiers, list) and len(tiers) == 0:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_EMPTY_TIERS, summary=summary)
    return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_NO_SALARY_COMPONENT, summary=summary)


def classify_lever_posting(posting: object) -> dict:
    if not isinstance(posting, dict):
        return classification(
            OBSERVATION_ERROR,
            REASON_SCHEMA_INCOMPATIBLE,
            error="Lever posting was not a JSON object",
        )
    summary = short_text(posting.get("salaryDescriptionPlain"))
    if "salaryRange" not in posting:
        return classification(
            OBSERVATION_EXPLICIT_EMPTY,
            REASON_FIELD_OMITTED,
            summary=summary,
        )
    raw = posting["salaryRange"]
    if raw is None:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_NULL, summary=summary)
    if not isinstance(raw, dict):
        return classification(
            OBSERVATION_ERROR,
            REASON_SCHEMA_INCOMPATIBLE,
            error="Lever salaryRange was not an object",
            summary=summary,
        )
    if len(raw) == 0:
        return classification(OBSERVATION_EXPLICIT_EMPTY, REASON_EMPTY_OBJECT, summary=summary)
    minimum = amount(raw.get("min"))
    maximum = amount(raw.get("max"))
    if minimum is None and maximum is None:
        return classification(
            OBSERVATION_EXPLICIT_EMPTY,
            REASON_NO_NUMERIC_BOUNDS,
            summary=summary,
        )
    ranges = [
        {
            "min": minimum,
            "max": maximum,
            "currency": currency_code(raw.get("currency")),
            "period": period_text(raw.get("interval")),
            "label": None,
            "summary": summary,
            "source": "salaryRange",
        }
    ]
    return classification(OBSERVATION_VALID, REASON_SALARY_BOUNDS, ranges, summary)


def _ashby_summary(raw: dict) -> str | None:
    for key in ("scrapeableCompensationSalarySummary", "compensationTierSummary"):
        text = short_text(raw.get(key))
        if text:
            return text
    return None


def _has_non_salary_component(raw: dict) -> bool:
    buckets = []
    tiers = raw.get("compensationTiers")
    if isinstance(tiers, list):
        for tier in tiers:
            if isinstance(tier, dict) and isinstance(tier.get("components"), list):
                buckets.extend(tier["components"])
    if isinstance(raw.get("summaryComponents"), list):
        buckets.extend(raw["summaryComponents"])
    for component in buckets:
        if isinstance(component, dict) and component.get("compensationType") not in (None, "Salary"):
            return True
    return False


def _salary_from_tiers(tiers: object) -> tuple[list[tuple[str | None, dict]], bool]:
    if not isinstance(tiers, list):
        return [], False
    found: list[tuple[str | None, dict]] = []
    saw = False
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        label = short_text(tier.get("title"))
        components = tier.get("components")
        if not isinstance(components, list):
            continue
        for component in components:
            if isinstance(component, dict) and component.get("compensationType") == "Salary":
                saw = True
                found.append((label, component))
    return found, saw


def _salary_from_summary_components(components: object) -> tuple[list[tuple[str | None, dict]], bool]:
    if not isinstance(components, list):
        return [], False
    found: list[tuple[str | None, dict]] = []
    saw = False
    for component in components:
        if isinstance(component, dict) and component.get("compensationType") == "Salary":
            saw = True
            found.append((None, component))
    return found, saw


def _salary_component_range(component: dict, label: str | None, source: str) -> dict | None:
    minimum = amount(component.get("minValue"))
    maximum = amount(component.get("maxValue"))
    if minimum is None and maximum is None:
        return None
    return {
        "min": minimum,
        "max": maximum,
        "currency": currency_code(component.get("currencyCode")),
        "period": period_text(component.get("interval")),
        "label": label,
        "summary": short_text(component.get("summary")),
        "source": source,
    }
