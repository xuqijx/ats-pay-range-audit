"""Load and atomically replace snapshot JSON. A failed replace leaves the previous file."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ats_pay_range_audit.constants import OBSERVATIONS, SCHEMA_VERSION, TOOL_NAME
from ats_pay_range_audit.errors import FetchError, UsageError


def json_dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    if "\x00" in str(path):
        raise UsageError("refusing a path that contains NUL")
    if path.is_symlink():
        raise UsageError(f"refusing to write through a symlink: {path}")
    parent = path.parent
    if parent == Path("") or not parent.is_dir():
        raise UsageError(f"directory does not exist: {parent}")
    if path.exists() and path.is_dir():
        raise UsageError(f"path is a directory: {path}")
    data = text.encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except UsageError:
        _discard(tmp)
        raise
    except OSError:
        _discard(tmp)
        raise
    except Exception:
        _discard(tmp)
        raise


def load_snapshot(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink():
        raise UsageError(f"refusing to read a snapshot through a symlink: {path}")
    if not path.is_file():
        raise UsageError(f"snapshot not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"could not read snapshot: {path}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError("parse_error", f"snapshot is not JSON: {path}") from exc
    _validate_snapshot(payload, path)
    return payload


def _validate_snapshot(payload: object, path: Path) -> None:
    if not isinstance(payload, dict):
        raise FetchError("schema_incompatible", f"snapshot {path} was not an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise FetchError(
            "schema_incompatible",
            f"snapshot {path} schema_version is not {SCHEMA_VERSION}",
        )
    if payload.get("tool") not in (None, TOOL_NAME):
        raise FetchError("schema_incompatible", f"snapshot {path} is not an {TOOL_NAME} file")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise FetchError("schema_incompatible", f"snapshot {path} has no jobs array")
    seen: set[tuple[str, str, str]] = set()
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise FetchError("schema_incompatible", f"snapshot job {index} was not an object")
        for key in ("provider", "board", "job_id", "observation", "ranges"):
            if key not in job:
                raise FetchError("schema_incompatible", f"snapshot job {index} is missing {key}")
        if job["observation"] not in OBSERVATIONS:
            raise FetchError("schema_incompatible", f"snapshot job {index} has an unknown observation")
        if not isinstance(job["ranges"], list):
            raise FetchError("schema_incompatible", f"snapshot job {index} ranges were not a list")
        identity = (str(job["provider"]), str(job["board"]), str(job["job_id"]))
        if identity in seen:
            raise FetchError("schema_incompatible", f"snapshot {path} repeats job id {identity[2]}")
        seen.add(identity)


def _discard(tmp: Path) -> None:
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        return
