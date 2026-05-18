#!/usr/bin/env python3
"""Prepare local AtCoder submissions CSV files for contest result tables."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from . import atcoder_metadata
except ImportError:
    import atcoder_metadata


RAW_COLUMNS = [
    "id",
    "epoch_second",
    "problem_id",
    "contest_id",
    "user_id",
    "language",
    "point",
    "length",
    "result",
    "execution_time",
]
RESULT_TABLE_COLUMNS = ["id", "epoch_second", "contest_id", "problem_id", "user_id", "result"]
IGNORED_RESULT_TABLE_RESULTS = {"CE", "IE", "WJ"}
DEFAULT_BUFFER_SIZE = 16 * 1024 * 1024
DEFAULT_PROGRESS_ROWS = 5_000_000


class AtCoderSubmissionsCsvError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def output_json(data: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        stdout_buffer = getattr(sys.stdout, "buffer", None)
        if stdout_buffer is not None:
            stdout_buffer.write(text.encode("utf-8"))
        else:
            sys.stdout.write(text)


def contests_json_default() -> Path:
    path = atcoder_metadata.bundled_resource_path("contests")
    if path is None:
        raise AtCoderSubmissionsCsvError("Bundled AtCoder contests metadata path is unavailable.")
    return path


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.expanduser().read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise AtCoderSubmissionsCsvError(f"Could not read JSON: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AtCoderSubmissionsCsvError(f"Invalid JSON: {path}: {exc}") from exc


def load_contests(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, dict):
        payload = payload.get("result")
    if not isinstance(payload, list):
        raise AtCoderSubmissionsCsvError(f"AtCoder contests metadata must be a list: {path}")

    contests = [item for item in payload if isinstance(item, dict)]
    if not contests:
        raise AtCoderSubmissionsCsvError(f"AtCoder contests metadata is empty: {path}")
    return contests


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_contest_windows(
    contests_path: Path,
    *,
    max_duration_seconds: int | None,
) -> tuple[dict[str, tuple[int, int]], int]:
    windows: dict[str, tuple[int, int]] = {}
    skipped = 0

    for contest in load_contests(contests_path):
        contest_id = contest.get("id")
        start = int_or_none(contest.get("start_epoch_second"))
        duration = int_or_none(contest.get("duration_second"))
        if not isinstance(contest_id, str) or start is None or duration is None:
            skipped += 1
            continue
        if duration < 0:
            skipped += 1
            continue
        if max_duration_seconds is not None and duration > max_duration_seconds:
            skipped += 1
            continue
        window = (start, start + duration)
        windows[contest_id] = window
        windows.setdefault(contest_id.lower(), window)

    if not windows:
        raise AtCoderSubmissionsCsvError("No usable contest windows were loaded.")
    return windows, skipped


def parse_header(line: str) -> list[str]:
    return [item.strip() for item in line.rstrip("\r\n").split(",")]


def require_raw_header(header: list[str]) -> None:
    if header != RAW_COLUMNS:
        got = ", ".join(header)
        expected = ", ".join(RAW_COLUMNS)
        raise AtCoderSubmissionsCsvError(
            "Unsupported submissions CSV header for fast processing.\n"
            f"expected: {expected}\n"
            f"got:      {got}"
        )


def parse_raw_submission_line(line: str) -> tuple[str, int, str, str, str, str] | None:
    prefix = line.rstrip("\r\n").split(",", 5)
    if len(prefix) != 6:
        return None

    submission_id, epoch_raw, problem_id, contest_id, user_id, rest = prefix
    tail = rest.rsplit(",", 4)
    if len(tail) != 5:
        return None

    try:
        epoch_second = int(epoch_raw)
    except ValueError:
        return None

    result = tail[3]
    return submission_id, epoch_second, contest_id, problem_id, user_id, result


def result_table_line(row: tuple[str, int, str, str, str, str]) -> str:
    submission_id, epoch_second, contest_id, problem_id, user_id, result = row
    return f"{submission_id},{epoch_second},{contest_id},{problem_id},{user_id},{result}\n"


def result_affects_table(result: str, *, keep_ignored_results: bool) -> bool:
    if keep_ignored_results:
        return True
    return bool(result) and result not in IGNORED_RESULT_TABLE_RESULTS


def resolve_path(value: Path | None, default: Path) -> Path:
    if value is None:
        return default
    return value.expanduser()


def ensure_output_path(path: Path, *, overwrite: bool, label: str) -> None:
    if path.exists() and not overwrite:
        raise AtCoderSubmissionsCsvError(f"{label} already exists; pass --overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_distinct(paths: list[Path]) -> None:
    resolved: dict[Path, Path] = {}
    for path in paths:
        key = path.expanduser().resolve()
        if key in resolved:
            raise AtCoderSubmissionsCsvError(f"Output paths must be distinct: {path}")
        resolved[key] = path


def print_progress(args: argparse.Namespace, message: str) -> None:
    if args.progress_rows != 0:
        print(message, file=sys.stderr, flush=True)


def prepare_result_table(args: argparse.Namespace) -> dict[str, Any]:
    input_path = args.input.expanduser().resolve()
    if not input_path.is_file():
        raise AtCoderSubmissionsCsvError(f"Input CSV is not a file: {input_path}")

    output_dir = (args.output_dir or input_path.parent).expanduser()
    contest_output = resolve_path(args.contest_output, output_dir / "contest_submissions.csv")
    result_output = resolve_path(
        args.result_output,
        output_dir / "contest_result_table_submissions.csv",
    )
    summary_output = resolve_path(
        args.summary_json,
        result_output.with_name(f"{result_output.stem}_summary.json"),
    )
    ensure_distinct([input_path, contest_output, result_output, summary_output])
    ensure_output_path(contest_output, overwrite=args.overwrite, label="Contest-time output CSV")
    ensure_output_path(result_output, overwrite=args.overwrite, label="Result-table output CSV")
    ensure_output_path(summary_output, overwrite=args.overwrite, label="Summary JSON")

    windows, skipped_contests = load_contest_windows(
        args.contests_json.expanduser().resolve(),
        max_duration_seconds=args.max_duration_seconds,
    )

    started = time.time()
    total = 0
    kept = 0
    outside = 0
    unknown_contest = 0
    malformed = 0
    ignored_results = 0

    with input_path.open("r", encoding="utf-8-sig", newline="", buffering=args.buffer_size) as src:
        header_line = src.readline()
        if not header_line:
            raise AtCoderSubmissionsCsvError(f"Input CSV is empty: {input_path}")
        require_raw_header(parse_header(header_line))

        with contest_output.open(
            "w",
            encoding="utf-8",
            newline="",
            buffering=args.buffer_size,
        ) as contest_dst, result_output.open(
            "w",
            encoding="utf-8",
            newline="",
            buffering=args.buffer_size,
        ) as result_dst:
            contest_dst.write(header_line)
            result_dst.write(",".join(RESULT_TABLE_COLUMNS) + "\n")

            for line in src:
                total += 1
                row = parse_raw_submission_line(line)
                if row is None:
                    malformed += 1
                    continue

                _submission_id, epoch_second, contest_id, _problem_id, _user_id, _result = row
                window = windows.get(contest_id) or windows.get(contest_id.lower())
                if window is None:
                    unknown_contest += 1
                    continue

                start, end = window
                if start <= epoch_second <= end:
                    contest_dst.write(line)
                    if result_affects_table(_result, keep_ignored_results=args.keep_ignored_results):
                        result_dst.write(result_table_line(row))
                    else:
                        ignored_results += 1
                    kept += 1
                else:
                    outside += 1

                if args.progress_rows > 0 and total % args.progress_rows == 0:
                    elapsed = time.time() - started
                    print_progress(
                        args,
                        (
                            f"processed={total:,} kept={kept:,} outside={outside:,} "
                            f"unknown={unknown_contest:,} elapsed={elapsed:.1f}s"
                        ),
                    )

    elapsed = time.time() - started
    summary = {
        "input": str(input_path),
        "contest_output": str(contest_output),
        "result_table_output": str(result_output),
        "contest_metadata": str(args.contests_json.expanduser().resolve()),
        "contest_windows": len(windows),
        "skipped_contests": skipped_contests,
        "filter": "start_epoch_second <= epoch_second <= start_epoch_second + duration_second",
        "kept_columns": RESULT_TABLE_COLUMNS,
        "dropped_columns": [name for name in RAW_COLUMNS if name not in RESULT_TABLE_COLUMNS],
        "ignored_result_table_results": sorted(IGNORED_RESULT_TABLE_RESULTS),
        "total_rows_without_header": total,
        "kept_rows": kept,
        "result_table_rows": kept - ignored_results,
        "ignored_result_table_rows": ignored_results,
        "outside_contest_rows": outside,
        "unknown_contest_rows": unknown_contest,
        "malformed_rows": malformed,
        "elapsed_seconds": round(elapsed, 3),
        "input_size_bytes": input_path.stat().st_size,
        "contest_output_size_bytes": contest_output.stat().st_size,
        "result_table_output_size_bytes": result_output.stat().st_size,
    }
    output_json(summary, summary_output)
    return summary


def filter_contest_time(args: argparse.Namespace) -> dict[str, Any]:
    input_path = args.input.expanduser().resolve()
    if not input_path.is_file():
        raise AtCoderSubmissionsCsvError(f"Input CSV is not a file: {input_path}")

    output_path = resolve_path(args.output, input_path.with_name("contest_submissions.csv"))
    summary_output = resolve_path(
        args.summary_json,
        output_path.with_name(f"{output_path.stem}_summary.json"),
    )
    ensure_distinct([input_path, output_path, summary_output])
    ensure_output_path(output_path, overwrite=args.overwrite, label="Contest-time output CSV")
    ensure_output_path(summary_output, overwrite=args.overwrite, label="Summary JSON")

    windows, skipped_contests = load_contest_windows(
        args.contests_json.expanduser().resolve(),
        max_duration_seconds=args.max_duration_seconds,
    )

    started = time.time()
    total = 0
    kept = 0
    outside = 0
    unknown_contest = 0
    malformed = 0

    with input_path.open("r", encoding="utf-8-sig", newline="", buffering=args.buffer_size) as src:
        header_line = src.readline()
        if not header_line:
            raise AtCoderSubmissionsCsvError(f"Input CSV is empty: {input_path}")
        require_raw_header(parse_header(header_line))

        with output_path.open("w", encoding="utf-8", newline="", buffering=args.buffer_size) as dst:
            dst.write(header_line)
            for line in src:
                total += 1
                row = parse_raw_submission_line(line)
                if row is None:
                    malformed += 1
                    continue

                _submission_id, epoch_second, contest_id, _problem_id, _user_id, _result = row
                window = windows.get(contest_id) or windows.get(contest_id.lower())
                if window is None:
                    unknown_contest += 1
                    continue

                start, end = window
                if start <= epoch_second <= end:
                    dst.write(line)
                    kept += 1
                else:
                    outside += 1

                if args.progress_rows > 0 and total % args.progress_rows == 0:
                    elapsed = time.time() - started
                    print_progress(
                        args,
                        (
                            f"processed={total:,} kept={kept:,} outside={outside:,} "
                            f"unknown={unknown_contest:,} elapsed={elapsed:.1f}s"
                        ),
                    )

    elapsed = time.time() - started
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "contest_metadata": str(args.contests_json.expanduser().resolve()),
        "contest_windows": len(windows),
        "skipped_contests": skipped_contests,
        "filter": "start_epoch_second <= epoch_second <= start_epoch_second + duration_second",
        "total_rows_without_header": total,
        "kept_rows": kept,
        "outside_contest_rows": outside,
        "unknown_contest_rows": unknown_contest,
        "malformed_rows": malformed,
        "elapsed_seconds": round(elapsed, 3),
        "input_size_bytes": input_path.stat().st_size,
        "output_size_bytes": output_path.stat().st_size,
    }
    output_json(summary, summary_output)
    return summary


def slim_result_table(args: argparse.Namespace) -> dict[str, Any]:
    input_path = args.input.expanduser().resolve()
    if not input_path.is_file():
        raise AtCoderSubmissionsCsvError(f"Input CSV is not a file: {input_path}")

    output_path = resolve_path(args.output, input_path.with_name("contest_result_table_submissions.csv"))
    summary_output = resolve_path(
        args.summary_json,
        output_path.with_name(f"{output_path.stem}_summary.json"),
    )
    ensure_distinct([input_path, output_path, summary_output])
    ensure_output_path(output_path, overwrite=args.overwrite, label="Result-table output CSV")
    ensure_output_path(summary_output, overwrite=args.overwrite, label="Summary JSON")

    started = time.time()
    rows = 0
    written = 0
    ignored_results = 0

    with input_path.open("r", encoding="utf-8-sig", newline="", buffering=args.buffer_size) as src:
        header_line = src.readline()
        if not header_line:
            raise AtCoderSubmissionsCsvError(f"Input CSV is empty: {input_path}")
        header = parse_header(header_line)
        with output_path.open("w", encoding="utf-8", newline="", buffering=args.buffer_size) as dst:
            dst.write(",".join(RESULT_TABLE_COLUMNS) + "\n")

            if header == RAW_COLUMNS:
                for line in src:
                    rows += 1
                    parsed = parse_raw_submission_line(line)
                    if parsed is None:
                        raise AtCoderSubmissionsCsvError(f"Malformed row at input data row {rows}.")
                    result = parsed[5]
                    if result_affects_table(result, keep_ignored_results=args.keep_ignored_results):
                        dst.write(result_table_line(parsed))
                        written += 1
                    else:
                        ignored_results += 1

                    if args.progress_rows > 0 and rows % args.progress_rows == 0:
                        elapsed = time.time() - started
                        print_progress(args, f"processed={rows:,} written={written:,} elapsed={elapsed:.1f}s")
            else:
                index = {name: position for position, name in enumerate(header)}
                missing = [name for name in RESULT_TABLE_COLUMNS if name not in index]
                if missing:
                    raise AtCoderSubmissionsCsvError(f"Missing columns: {', '.join(missing)}")

                keep_indexes = [index[name] for name in RESULT_TABLE_COLUMNS]
                result_index = index["result"]
                reader = csv.reader(src)
                for row in reader:
                    rows += 1
                    if len(row) <= max(keep_indexes):
                        raise AtCoderSubmissionsCsvError(f"Malformed row at input data row {rows}.")
                    result = row[result_index]
                    if result_affects_table(result, keep_ignored_results=args.keep_ignored_results):
                        dst.write(",".join(row[index] for index in keep_indexes) + "\n")
                        written += 1
                    else:
                        ignored_results += 1

                    if args.progress_rows > 0 and rows % args.progress_rows == 0:
                        elapsed = time.time() - started
                        print_progress(args, f"processed={rows:,} written={written:,} elapsed={elapsed:.1f}s")

    elapsed = time.time() - started
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "kept_columns": RESULT_TABLE_COLUMNS,
        "dropped_columns": [name for name in header if name not in RESULT_TABLE_COLUMNS],
        "rows_without_header": rows,
        "output_rows_without_header": written,
        "ignored_result_table_results": sorted(IGNORED_RESULT_TABLE_RESULTS),
        "ignored_result_table_rows": ignored_results,
        "elapsed_seconds": round(elapsed, 3),
        "input_size_bytes": input_path.stat().st_size,
        "output_size_bytes": output_path.stat().st_size,
    }
    output_json(summary, summary_output)
    return summary


def add_io_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True, type=Path, help="Input AtCoder submissions CSV.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write the operation summary to this path. Defaults next to the output CSV.",
    )
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=DEFAULT_BUFFER_SIZE,
        help="File buffer size in bytes.",
    )
    parser.add_argument(
        "--progress-rows",
        type=int,
        default=DEFAULT_PROGRESS_ROWS,
        help="Print progress to stderr every N rows. Use 0 to disable.",
    )


def add_contest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--contests-json",
        type=Path,
        default=contests_json_default(),
        help="AtCoder contests metadata JSON. Defaults to references/atcoder-cache/contests.json.",
    )
    parser.add_argument(
        "--max-duration-seconds",
        type=int,
        help="Ignore contests whose duration is longer than this many seconds.",
    )


def add_result_table_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--keep-ignored-results",
        action="store_true",
        help="Keep CE, IE, and WJ rows even though they do not affect README result tables.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Filter AtCoder submissions CSVs and keep result-table columns."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare-result-table",
        help="Read raw submissions.csv once and write both contest-time and result-table CSVs.",
    )
    add_io_args(prepare)
    add_contest_args(prepare)
    add_result_table_filter_args(prepare)
    prepare.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for default outputs. Defaults to the input CSV directory.",
    )
    prepare.add_argument(
        "--contest-output",
        type=Path,
        help="Contest-time full CSV output. Defaults to contest_submissions.csv.",
    )
    prepare.add_argument(
        "--result-output",
        type=Path,
        help="Result-table slim CSV output. Defaults to contest_result_table_submissions.csv.",
    )

    filter_parser = subparsers.add_parser(
        "filter-contest-time",
        help="Keep only submissions made during the official contest window.",
    )
    add_io_args(filter_parser)
    add_contest_args(filter_parser)
    filter_parser.add_argument(
        "--output",
        type=Path,
        help="Contest-time full CSV output. Defaults to contest_submissions.csv.",
    )

    slim = subparsers.add_parser(
        "slim-result-table",
        help="Keep only columns needed for README result table generation.",
    )
    add_io_args(slim)
    add_result_table_filter_args(slim)
    slim.add_argument(
        "--output",
        type=Path,
        help="Slim CSV output. Defaults to contest_result_table_submissions.csv.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare-result-table":
            summary = prepare_result_table(args)
        elif args.command == "filter-contest-time":
            summary = filter_contest_time(args)
        elif args.command == "slim-result-table":
            summary = slim_result_table(args)
        else:
            parser.error(f"Unknown command: {args.command}")
        output_json(summary, None)
    except AtCoderSubmissionsCsvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
