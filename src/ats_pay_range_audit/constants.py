"""Shared status vocabulary and the coverage sentence the report always prints."""

TOOL_NAME = "ats-pay-range-audit"
SCHEMA_VERSION = 1
SELECTED_DATE = "2026-11-11"
LAUNCH_WINDOW_END = "2026-11-18"

OBSERVATION_VALID = "valid"
OBSERVATION_EXPLICIT_EMPTY = "explicit_empty"
OBSERVATION_UNKNOWN = "unknown"
OBSERVATION_ERROR = "error"
OBSERVATIONS = (
    OBSERVATION_VALID,
    OBSERVATION_EXPLICIT_EMPTY,
    OBSERVATION_UNKNOWN,
    OBSERVATION_ERROR,
)

STRUCTURED_PRESENT = "present"
STRUCTURED_ABSENT = "absent"
STRUCTURED_UNKNOWN = "unknown"
STRUCTURED_ERROR = "error"

REASON_SALARY_BOUNDS = "salary_bounds"
REASON_NULL = "null"
REASON_EMPTY_OBJECT = "empty_object"
REASON_EMPTY_ARRAY = "empty_array"
REASON_EMPTY_TIERS = "empty_tiers"
REASON_NO_NUMERIC_BOUNDS = "no_numeric_bounds"
REASON_NO_SALARY_COMPONENT = "no_salary_component"
REASON_SUMMARY_ONLY = "summary_only"
REASON_FIELD_OMITTED = "field_omitted"
REASON_FIELD_NOT_IN_RESPONSE = "field_not_in_response"
REASON_DETAIL_BUDGET_EXHAUSTED = "detail_budget_exhausted"
REASON_PROVIDER_UNSUPPORTED = "provider_unsupported"
REASON_HTTP_ERROR = "http_error"
REASON_HTTP_429 = "http_429"
REASON_PARSE_ERROR = "parse_error"
REASON_SCHEMA_INCOMPATIBLE = "schema_incompatible"
REASON_MISSING_JOB_IDENTITY = "missing_job_identity"
REASON_REDIRECT = "redirect_blocked"
REASON_TIMEOUT = "timeout"
REASON_DUPLICATE_JOB_ID = "duplicate_job_id"

DENOMINATOR_EXPLANATION = (
    "Coverage numerator is jobs with a valid structured salary range. "
    "Denominator is valid plus explicit_empty only. "
    "unknown is excluded: the documented field was not observed, "
    "which is not evidence that the employer published no pay. "
    "error is excluded and is never counted as no pay. "
    "An empty compensation object is explicit_empty, not a valid range. "
    "If the denominator is 0, ratio is null and is not 0%."
)

GREENHOUSE_METHODOLOGY = (
    "Checked 2026-11-11 against https://docs.greenhouse.io/job-board and "
    "https://support.greenhouse.io/hc/en-us/articles/10028084062491-Add-pay-transparency-to-a-job-post. "
    "List jobs (GET /v1/boards/{board_token}/jobs) documents only the content query parameter. "
    "The retrieve-a-job query table documents pay_transparency=true. "
    "That parameter adds the response array pay_input_ranges. "
    "pay_input_ranges is not sent as its own query parameter, because that table does not list it as one. "
    "The support article's phrase 'pay_transparency and/or pay_input_ranges' is not treated as a second query name. "
    "This tool does not send pay_transparency on the list call and ignores any pay fields on list items, "
    "so a list that omits pay_input_ranges or shows an empty array is not treated as no salary. "
    "A missing pay_input_ranges key on the detail response is unknown. "
    "Null, an empty array, an empty object, or entries without numeric cents are explicit_empty. "
    "content and blurb text are not parsed. Harvest is not called."
)

ASHBY_METHODOLOGY = (
    "Checked 2026-11-11 against https://developers.ashbyhq.com/docs/public-job-posting-api. "
    "GET /posting-api/job-board/{name}?includeCompensation=true. "
    "Only jobs[].compensation is read. A top-level compensation object is not copied onto jobs. "
    "A Salary component with a numeric minValue and/or maxValue is a valid range. "
    "Null, an empty object, summary text, equity, bonus, and commission are not valid salary ranges. "
    "Summary strings are stored and are not parsed for numbers. "
    "A missing compensation key is unknown, not an empty range."
)

LEVER_METHODOLOGY = (
    "Checked 2026-11-11 against https://github.com/lever/postings-api. "
    "GET /v0/postings/{site}?mode=json on api.lever.co or, when region is eu, api.eu.lever.co. "
    "salaryRange (currency, interval, min, max) is an optional field on that list payload. "
    "Omitting it is explicit_empty reason field_omitted and structured_range absent, "
    "because this endpoint is the documented carrier of the field. "
    "absent names a missing structured object. It does not say the employer published no pay, "
    "and it is not a legal conclusion. "
    "That is different from a Greenhouse list, which does not document a pay field. "
    "Null, an empty object, or no numeric min/max are explicit_empty with their own reasons. "
    "description and salaryDescription HTML are not parsed. Application POST is not implemented."
)

METHODOLOGY = {
    "greenhouse": GREENHOUSE_METHODOLOGY,
    "ashby": ASHBY_METHODOLOGY,
    "lever": LEVER_METHODOLOGY,
    "coverage_denominator": DENOMINATOR_EXPLANATION,
    "legal": (
        "This report describes structured fields returned by a public job-board GET. "
        "It is not a legal opinion and cannot tell whether a pay-transparency statute applies."
    ),
}
