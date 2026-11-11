"""Locate and copy the fictional fixtures shipped with the source tree or the wheel."""

from __future__ import annotations

import shutil
from pathlib import Path

from ats_pay_range_audit.errors import UsageError


def bundled_root() -> Path:
    """Directory that contains `fixtures/` and `examples/`.

    An installed wheel has them under the package. A source checkout keeps them
    at the repository root, which is also how an unpacked sdist is laid out.
    """

    installed = Path(__file__).resolve().parent / "bundled"
    if (installed / "fixtures").is_dir() and (installed / "examples").is_dir():
        return installed
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "fixtures").is_dir() and (checkout / "examples").is_dir():
        return checkout
    raise UsageError("example boards are not available in this installation")


def write_examples(dest: Path) -> None:
    """Copy fixtures and examples into a new directory. Relative fixture paths keep working."""

    if "\x00" in str(dest):
        raise UsageError("refusing a path that contains NUL")
    if dest.exists() or dest.is_symlink():
        raise UsageError(f"refusing to write into an existing path: {dest}")
    parent = dest.parent
    if not parent.is_dir():
        raise UsageError(f"directory does not exist: {parent}")
    if parent.is_symlink():
        raise UsageError(f"refusing to write through a symlink: {parent}")
    root = bundled_root()
    dest.mkdir()
    shutil.copytree(root / "fixtures", dest / "fixtures")
    shutil.copytree(root / "examples", dest / "examples")
