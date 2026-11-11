"""Command line. Network stays off unless --live is set and a board has no fixture."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ats_pay_range_audit import __version__
from ats_pay_range_audit.audit import report_has_errors, run_audit
from ats_pay_range_audit.boards import load_boards
from ats_pay_range_audit.bundle import write_examples
from ats_pay_range_audit.diffing import diff_snapshots
from ats_pay_range_audit.errors import FetchError, UsageError
from ats_pay_range_audit.fixtures import FixtureRaw
from ats_pay_range_audit.http_client import LiveRaw, PoliteSession, resolved_intervals
from ats_pay_range_audit.render import dump_json, render_diff, render_report
from ats_pay_range_audit.snapshot import atomic_write_text, load_snapshot


def main(argv: list[str] | None = None) -> None:
    try:
        code = run(argv)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = 2
    except BrokenPipeError:
        code = 0
    raise SystemExit(code)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ats-pay-range-audit",
        description=(
            "Read-only audit of structured salary fields on public Greenhouse, Ashby, and Lever boards. "
            "Not a legal opinion, not a job matcher, and not an application bot."
        ),
    )
    parser.add_argument("boards", nargs="?", help="YAML (or JSON) list of provider plus board slug")
    parser.add_argument("--diff", nargs=2, metavar=("OLD", "NEW"), help="compare two snapshot JSON files")
    parser.add_argument("--json", action="store_true", help="print the machine-readable report")
    parser.add_argument("--save", metavar="PATH", help="atomically write the JSON report to PATH")
    parser.add_argument(
        "--live",
        action="store_true",
        help="allow documented public GETs for boards that have no fixture",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=500,
        help="cap Greenhouse retrieve-a-job calls (default 500, -1 for no cap, max 10000)",
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=None,
        help="seconds between live calls. Lever never goes below 1s; Greenhouse and Ashby never below 0.5s",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="per-request timeout in seconds (max 120)")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument(
        "--write-examples",
        metavar="DIR",
        help="copy the fictional fixtures and example boards into a new directory and exit",
    )
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.write_examples:
        if args.boards or args.diff or args.live or args.save or args.json:
            raise UsageError("--write-examples is used by itself")
        destination = Path(args.write_examples)
        write_examples(destination)
        print(f"wrote fictional examples to {destination}")
        print(f"ats-pay-range-audit {destination / 'examples' / 'ashby-all-ranges.yaml'}")
        return 0
    if args.diff and args.boards:
        raise UsageError("pass either a boards file or --diff, not both")
    if args.diff:
        return _run_diff(args)
    if not args.boards:
        raise UsageError("a boards file is required, or pass --diff OLD NEW")
    if args.max_details < -1 or args.max_details > 10000:
        raise UsageError("--max-details must be -1 or an integer from 0 through 10000")
    if args.timeout <= 0 or args.timeout > 120:
        raise UsageError("--timeout must be greater than 0 and at most 120")
    boards = load_boards(Path(args.boards))
    intervals = resolved_intervals(args.min_interval)
    network = any(board.fixture is None for board in boards)
    if network and not args.live:
        raise UsageError("refusing network because --live was not set. Add a fixture or pass --live")
    live_session: PoliteSession | None = None

    def session_for(board):
        nonlocal live_session
        if board.fixture is not None:
            return PoliteSession(
                FixtureRaw(board.fixture, board.provider),
                sleeper=lambda _seconds: None,
                clock=time.monotonic,
                min_intervals=intervals,
                pace=False,
            )
        if live_session is None:
            live_session = PoliteSession(
                LiveRaw(args.timeout),
                sleeper=time.sleep,
                clock=time.monotonic,
                min_intervals=intervals,
                pace=True,
            )
        return live_session

    report = run_audit(
        boards,
        session_for,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        max_details=args.max_details,
        network=bool(network and args.live),
    )
    text = dump_json(report) if args.json else render_report(report)
    _save(args.save, dump_json(report))
    sys.stdout.write(text)
    return 1 if report_has_errors(report) else 0


def _run_diff(args) -> int:
    try:
        old = load_snapshot(Path(args.diff[0]))
        new = load_snapshot(Path(args.diff[1]))
    except FetchError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    diff = diff_snapshots(old, new)
    text = dump_json(diff) if args.json else render_diff(diff)
    _save(args.save, dump_json(diff))
    sys.stdout.write(text)
    return 0


def _save(path: str | None, text: str) -> None:
    if not path:
        return
    try:
        atomic_write_text(Path(path), text)
    except UsageError:
        raise
    except OSError as exc:
        raise UsageError(f"could not write {path}: {exc}") from exc
