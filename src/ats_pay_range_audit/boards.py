"""Load a user board list. Fetch targets are slugs, never arbitrary URLs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ats_pay_range_audit.errors import UsageError
from ats_pay_range_audit.urls import require_region, require_slug

_ALLOWED_KEYS = {"provider", "board", "name", "region", "fixture", "token", "slug", "site"}
_URL_KEYS = {"url", "endpoint", "base_url", "host", "href"}
_PROVIDERS = {"greenhouse", "ashby", "lever"}


@dataclass(frozen=True)
class Board:
    provider: str
    board: str
    name: str
    region: str
    fixture: Path | None


def load_boards(path: Path) -> list[Board]:
    path = Path(path)
    if path.is_symlink():
        raise UsageError(f"refusing to read a symlink: {path}")
    if not path.is_file():
        raise UsageError(f"boards file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"could not read boards file: {path}") from exc
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UsageError(f"boards file is not JSON: {path}") from exc
    else:
        payload = _load_yaml(text, path)
    if not isinstance(payload, dict) or not isinstance(payload.get("boards"), list):
        raise UsageError("boards file must be a mapping with a boards list")
    if not payload["boards"]:
        raise UsageError("boards list is empty")
    boards = []
    for index, raw in enumerate(payload["boards"], start=1):
        boards.append(_one_board(raw, index, path.parent))
    return boards


def _load_yaml(text: str, path: Path):
    try:
        import yaml
    except ImportError as exc:
        raise UsageError("PyYAML is required to read a YAML boards file") from exc
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise UsageError(f"boards file is not valid YAML: {path}") from exc
    return payload


def _one_board(raw: object, index: int, base: Path) -> Board:
    if not isinstance(raw, dict):
        raise UsageError(f"board {index} was not a mapping")
    unexpected_url = _URL_KEYS.intersection(raw)
    if unexpected_url:
        raise UsageError(
            f"board {index} uses {sorted(unexpected_url)[0]}, which is not accepted. "
            "Pass provider and board slug only"
        )
    unknown = set(raw) - _ALLOWED_KEYS
    if unknown:
        raise UsageError(f"board {index} has unsupported keys: {', '.join(sorted(unknown))}")
    provider = raw.get("provider")
    if provider not in _PROVIDERS:
        raise UsageError(f"board {index} provider must be greenhouse, ashby, or lever")
    slug = _slug_from(raw, index)
    require_slug(slug, f"board {index}")
    region = require_region(raw.get("region"))
    if provider != "lever" and raw.get("region") not in (None, "", "global"):
        raise UsageError(f"board {index} region is only used for Lever")
    name = raw.get("name") or slug
    if not isinstance(name, str) or not name.strip():
        raise UsageError(f"board {index} name must be a string")
    fixture = _fixture_path(raw.get("fixture"), index, base)
    return Board(provider=provider, board=slug, name=name.strip(), region=region, fixture=fixture)


def _slug_from(raw: dict, index: int) -> str:
    found = []
    for key in ("board", "token", "slug", "site"):
        if key in raw and raw[key] is not None:
            found.append(raw[key])
    if not found:
        raise UsageError(f"board {index} needs a board slug")
    if any(not isinstance(item, str) for item in found):
        raise UsageError(f"board {index} slug must be a string")
    if len(set(found)) != 1:
        raise UsageError(f"board {index} has conflicting slug fields")
    return found[0]


def _fixture_path(value: object, index: int, base: Path) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise UsageError(f"board {index} fixture must be a file path")
    candidate = Path(value)
    if candidate.is_symlink():
        raise UsageError(f"board {index} fixture is a symlink")
    resolved = candidate if candidate.is_absolute() else (base / candidate)
    if resolved.is_symlink():
        raise UsageError(f"board {index} fixture is a symlink")
    if not resolved.is_file():
        raise UsageError(f"board {index} fixture not found: {resolved}")
    return resolved
