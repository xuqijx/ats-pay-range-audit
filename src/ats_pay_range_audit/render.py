"""Text and JSON renderers. The JSON document is the snapshot."""

from __future__ import annotations

from ats_pay_range_audit.snapshot import json_dump


def render_report(report: dict) -> str:
    coverage = report["coverage"]
    lines = [
        f"{report['tool']} {report['tool_version']}",
        report["legal"],
        (
            f"coverage {coverage['ratio'] or 'undefined'}  "
            f"percent {coverage['percent'] if coverage['percent'] is not None else 'undefined'}  "
            f"unknown {coverage['unknown']}  errors {coverage['error']}"
        ),
        coverage["explanation"],
        "",
    ]
    for board in report["boards"]:
        state = "ok" if board["ok"] else f"error reason={board['reason']} {board['error']}"
        notes = ",".join(board["notes"]) if board["notes"] else "-"
        lines.append(
            f"[{board['provider']}] {board['company']} / {board['board']}  {state}  notes={notes}"
        )
    lines.append("")
    for job in report["jobs"]:
        salary = _salary_text(job)
        lines.append(
            f"{job['provider']}\t{job['board']}\t{job['job_id']}\t{job['title']}\t"
            f"observation={job['observation']}\treason={job['reason']}\t"
            f"structured_range={job['structured_range']}\t{salary}"
        )
    lines.append("")
    return "\n".join(lines)


def render_diff(diff: dict) -> str:
    lines = [
        f"{diff['tool']} diff",
        diff["note"],
        (
            f"bounds_changed {len(diff['bounds_changed'])}  "
            f"became_valid {len(diff['became_valid'])}  "
            f"became_empty {len(diff['became_empty'])}  "
            f"jobs_added {len(diff['jobs_added'])}  "
            f"jobs_removed {len(diff['jobs_removed'])}  "
            f"newly_observed {len(diff['newly_observed'])}  "
            f"unresolved {len(diff['unresolved'])}  "
            f"unchanged {diff['unchanged_count']}"
        ),
        "",
    ]
    for label in (
        "bounds_changed",
        "became_valid",
        "became_empty",
        "jobs_added",
        "jobs_removed",
        "newly_observed",
        "unresolved",
        "presentation_changed",
        "title_changed",
    ):
        rows = diff[label]
        if not rows:
            continue
        lines.append(label)
        for row in rows:
            if "before" in row and "after" in row:
                before = row["before"]
                after = row["after"]
                lines.append(
                    f"  {before['provider']} {before['board']} {before['job_id']} "
                    f"{before['observation']} -> {after['observation']} "
                    f"{_salary_text(before)} -> {_salary_text(after)}"
                )
            else:
                lines.append(
                    f"  {row['provider']} {row['board']} {row['job_id']} "
                    f"observation={row['observation']} {_salary_text(row)}"
                )
        lines.append("")
    return "\n".join(lines)


def dump_json(payload: dict) -> str:
    return json_dump(payload)


def _salary_text(job: dict) -> str:
    if not job.get("ranges"):
        summary = job.get("summary") or ""
        return summary
    parts = []
    for item in job["ranges"]:
        parts.append(
            f"{item.get('min')}-{item.get('max')} {item.get('currency') or ''} {item.get('period') or ''}".strip()
        )
    return "; ".join(parts)
