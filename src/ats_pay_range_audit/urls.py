"""Build the documented public GET URLs. Callers never supply a fetch URL."""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

from ats_pay_range_audit.errors import UsageError

SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
GREENHOUSE_JOB_ID = re.compile(r"^[0-9]{1,18}$")

HOSTS = {
    "greenhouse": "boards-api.greenhouse.io",
    "ashby": "api.ashbyhq.com",
    "lever": "api.lever.co",
    "lever-eu": "api.eu.lever.co",
}

_ALLOWED = {
    "greenhouse": {HOSTS["greenhouse"]},
    "ashby": {HOSTS["ashby"]},
    "lever": {HOSTS["lever"], HOSTS["lever-eu"]},
}

_PREFIX = {
    "greenhouse": "/v1/boards/",
    "ashby": "/posting-api/job-board/",
    "lever": "/v0/postings/",
}

DISPLAY_HOSTS = {
    "greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io"},
    "ashby": {"jobs.ashbyhq.com"},
    "lever": {"jobs.lever.co", "jobs.eu.lever.co"},
}


def require_slug(value: object, label: str) -> str:
    if not isinstance(value, str) or SLUG.fullmatch(value) is None:
        raise UsageError(
            f"{label} must match {SLUG.pattern} so it can only be a path segment, not a URL"
        )
    return value


def require_region(value: object) -> str:
    if value is None or value == "":
        return "global"
    if value not in ("global", "eu"):
        raise UsageError("Lever region must be global or eu")
    return str(value)


def greenhouse_list_url(board: str) -> str:
    token = require_slug(board, "Greenhouse board token")
    return f"https://{HOSTS['greenhouse']}/v1/boards/{quote(token, safe='')}/jobs"


def greenhouse_detail_url(board: str, job_id: str) -> str:
    token = require_slug(board, "Greenhouse board token")
    if GREENHOUSE_JOB_ID.fullmatch(job_id) is None:
        raise UsageError("Greenhouse job id is not a decimal id")
    # The Job Board API query table names pay_transparency. pay_input_ranges is the
    # response array, not a second query parameter. Nothing is added on the list URL.
    query = "pay_transparency=true"
    return (
        f"https://{HOSTS['greenhouse']}/v1/boards/{quote(token, safe='')}"
        f"/jobs/{quote(job_id, safe='')}?{query}"
    )


def ashby_board_url(board: str) -> str:
    slug = require_slug(board, "Ashby board name")
    return (
        f"https://{HOSTS['ashby']}/posting-api/job-board/"
        f"{quote(slug, safe='')}?includeCompensation=true"
    )


def lever_board_url(board: str, region: str) -> str:
    site = require_slug(board, "Lever site name")
    region = require_region(region)
    host = HOSTS["lever-eu"] if region == "eu" else HOSTS["lever"]
    return f"https://{host}/v0/postings/{quote(site, safe='')}?mode=json"


def greenhouse_canonical_job_url(board: str, job_id: str) -> str:
    token = require_slug(board, "Greenhouse board token")
    if GREENHOUSE_JOB_ID.fullmatch(job_id) is None:
        raise UsageError("Greenhouse job id is not a decimal id")
    return f"https://boards.greenhouse.io/{quote(token, safe='')}/jobs/{quote(job_id, safe='')}"


def assert_fetch_url(url: str, provider: str) -> None:
    """Reject anything that is not a URL this package just built."""

    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
        raise UsageError("refusing a non-https or credentialed URL")
    host = parsed.hostname
    if host not in _ALLOWED.get(provider, set()):
        raise UsageError(f"refusing host {host!r} for {provider}")
    if parsed.port not in (None, 443):
        raise UsageError("refusing a non-default port")
    if not parsed.path.startswith(_PREFIX[provider]):
        raise UsageError("refusing a path outside the documented prefix")
    if ".." in parsed.path.split("/"):
        raise UsageError("refusing a dotted path segment")
    allowed_keys = {
        "greenhouse": {"pay_transparency"},
        "ashby": {"includeCompensation"},
        "lever": {"mode"},
    }[provider]
    if parsed.query:
        for part in parsed.query.split("&"):
            key, separator, value = part.partition("=")
            if separator != "=" or key not in allowed_keys or not value:
                raise UsageError("refusing an unexpected query parameter")


def public_https_url(value: object, provider: str) -> str | None:
    """Keep a provider-hosted https URL for display. Never fetch it."""

    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    if parsed.hostname not in DISPLAY_HOSTS.get(provider, set()):
        return None
    if parsed.port not in (None, 443):
        return None
    return value
