#!/usr/bin/env python3
"""Create or update contest README entries for CP publish workflows."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ENTRY_RE = re.compile(r"^(\S+)\s*/\s*Rating\s*:\s*(.*?)\s*/\s*(.+?)\s*$")
RESULTS_HEADING = "## Results"
SOLUTIONS_HEADING = "## Solutions"
TAG_MAP_PATH = Path(__file__).resolve().parents[2] / "references" / "solvedac-tag-map.json"


class ReadmeUpdateError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


@dataclass
class Entry:
    problem_id: str
    rating: str
    tags: str

    def line(self) -> str:
        return f"{self.problem_id} / Rating : {self.rating} / {self.tags}"


@dataclass
class ResultRow:
    problem_id: str
    wrong_attempts: int
    accepted_at_seconds: int | None

    def line(self) -> str:
        return (
            f"| {self.problem_id} | {self.wrong_attempts} | "
            f"{format_accepted_time(self.accepted_at_seconds)} |"
        )


def normalize_problem_id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ReadmeUpdateError("problem id is required.")
    if cleaned.lower() == "ex":
        return "Ex"
    return cleaned.upper()


def normalize_rating(value: str | None) -> str:
    if value is None:
        return "$-$"

    cleaned = value.strip()
    if not cleaned or cleaned in {"-", "$-"}:
        return "$-$"

    if cleaned.startswith("$") and cleaned.endswith("$"):
        inner = cleaned[1:-1].strip()
        return "$-$" if inner == "-" else f"${inner}$"

    return f"${cleaned}$"


def load_tag_map() -> dict[str, str]:
    try:
        payload = json.loads(TAG_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadmeUpdateError(f"Could not load README tag map: {TAG_MAP_PATH}") from exc

    tags = payload.get("tags")
    if not isinstance(tags, dict):
        raise ReadmeUpdateError(f"README tag map has no tags object: {TAG_MAP_PATH}")

    result: dict[str, str] = {}
    for key, value in tags.items():
        if isinstance(key, str) and isinstance(value, str) and key and value:
            result[key] = value
    if not result:
        raise ReadmeUpdateError(f"README tag map is empty: {TAG_MAP_PATH}")
    return result


def normalize_tag_key(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    return re.sub(r"_+", "_", lowered).strip("_")


def normalize_readme_tag(value: str, tag_map: dict[str, str]) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ReadmeUpdateError("README tag must not be empty.")

    allowed_values = set(tag_map.values())
    if cleaned in allowed_values:
        return cleaned

    key = normalize_tag_key(cleaned)
    if key in tag_map:
        return tag_map[key]

    raise ReadmeUpdateError(
        f"Unsupported README tag: {cleaned}. "
        "Use a tag name or solved.ac key from references/solvedac-tag-map.json."
    )


def normalize_tags(raw_tags: str | None, repeated_tags: list[str] | None) -> str:
    raw_values: list[str] = []

    if raw_tags:
        raw_values.extend(part.strip() for part in raw_tags.split(","))
    if repeated_tags:
        raw_values.extend(part.strip() for part in repeated_tags)

    raw_values = [tag for tag in raw_values if tag]
    if not raw_values:
        raise ReadmeUpdateError("at least one tag is required.")

    tag_map = load_tag_map()
    tags = [normalize_readme_tag(tag, tag_map) for tag in raw_values]
    return ", ".join(tags)


def normalize_wrong_attempts(value: Any) -> int:
    try:
        attempts = int(value)
    except (TypeError, ValueError) as exc:
        raise ReadmeUpdateError(f"wrong attempts must be an integer, got: {value!r}") from exc
    if attempts < 0:
        raise ReadmeUpdateError("wrong attempts must not be negative.")
    return attempts


def normalize_accepted_seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned in {"-", "null", "None"}:
            return None
        if ":" in cleaned:
            parts = cleaned.split(":")
            if len(parts) not in {2, 3}:
                raise ReadmeUpdateError(f"accepted time must be seconds, MM:SS, HH:MM:SS, or '-', got: {value!r}")
            try:
                numbers = [int(part) for part in parts]
            except ValueError as exc:
                raise ReadmeUpdateError(f"accepted time contains a non-integer part: {value!r}") from exc
            if len(numbers) == 2:
                minutes, seconds = numbers
                hours = 0
            else:
                hours, minutes, seconds = numbers
            total = hours * 3600 + minutes * 60 + seconds
            if total < 0:
                raise ReadmeUpdateError("accepted time must not be negative.")
            return total
        value = cleaned

    try:
        seconds = int(value)
    except (TypeError, ValueError) as exc:
        raise ReadmeUpdateError(f"accepted time must be seconds, MM:SS, HH:MM:SS, or '-', got: {value!r}") from exc
    if seconds < 0:
        raise ReadmeUpdateError("accepted time must not be negative.")
    return seconds


def format_accepted_time(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    hours, remainder = divmod(seconds, 3600)
    minutes, second = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{second:02d}"


def parse_entry(line: str) -> Entry | None:
    match = ENTRY_RE.match(line)
    if not match:
        return None
    return Entry(
        problem_id=normalize_problem_id(match.group(1)),
        rating=normalize_rating(match.group(2)),
        tags=normalize_tags(match.group(3), None),
    )


def parse_result_row(line: str) -> ResultRow | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None

    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if len(cells) != 3:
        return None

    first = cells[0].lower()
    if first in {"problem", "---"}:
        return None
    if all(set(cell) <= {"-", ":", " "} for cell in cells):
        return None

    return ResultRow(
        problem_id=normalize_problem_id(cells[0]),
        wrong_attempts=normalize_wrong_attempts(cells[1]),
        accepted_at_seconds=normalize_accepted_seconds(cells[2]),
    )


def is_known_result_table_markup(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return False
    cells = [cell.strip().lower() for cell in stripped.strip("|").split("|")]
    if cells in (["problem", "wrong", "ac time"], ["problem", "wrong attempts", "accepted at"]):
        return True
    return all(cell and set(cell) <= {"-", ":", " "} for cell in cells)


def problem_sort_key(problem_id: str) -> tuple[int, int, str]:
    if problem_id == "Ex":
        return (1000, 0, problem_id)

    match = re.match(r"^([A-Z]+)(\d*)$", problem_id)
    if match:
        letters, digits = match.groups()
        letter_score = 0
        for char in letters:
            letter_score = letter_score * 26 + (ord(char) - ord("A") + 1)
        number = int(digits) if digits else -1
        return (letter_score, number, problem_id)

    if problem_id.isdigit():
        return (2000, int(problem_id), problem_id)

    return (3000, 0, problem_id)


def read_existing(readme_path: Path) -> tuple[str | None, list[Entry], list[ResultRow], list[str]]:
    if not readme_path.exists():
        return None, [], [], []

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None, [], [], []

    header = lines[0].strip()
    entries: list[Entry] = []
    result_rows: list[ResultRow] = []
    unknown_lines: list[str] = []

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {RESULTS_HEADING, SOLUTIONS_HEADING}:
            continue
        if stripped.startswith("|"):
            result_row = parse_result_row(stripped)
            if result_row is not None:
                result_rows.append(result_row)
            elif not is_known_result_table_markup(stripped):
                unknown_lines.append(stripped)
            continue

        entry = parse_entry(stripped)
        if entry is None:
            unknown_lines.append(stripped)
        else:
            entries.append(entry)

    return header, entries, result_rows, unknown_lines


def render_readme(header: str, entries: list[Entry], result_rows: list[ResultRow]) -> str:
    lines = [header, ""]

    sorted_results = sorted(result_rows, key=lambda item: problem_sort_key(item.problem_id))
    sorted_entries = sorted(entries, key=lambda item: problem_sort_key(item.problem_id))

    if sorted_results:
        lines.extend(
            [
                RESULTS_HEADING,
                "",
                "| Problem | Wrong | AC Time |",
                "| --- | ---: | --- |",
            ]
        )
        lines.extend(row.line() for row in sorted_results)
        if sorted_entries:
            lines.extend(["", SOLUTIONS_HEADING, ""])

    for index, entry in enumerate(sorted_entries):
        if index:
            lines.append("")
        lines.append(entry.line())
    return "\n".join(lines).rstrip() + "\n"


def update_entries(entries: list[Entry], new_entry: Entry) -> tuple[list[Entry], str]:
    updated: list[Entry] = []
    action = "added"
    replaced = False

    for entry in entries:
        if entry.problem_id == new_entry.problem_id:
            updated.append(new_entry)
            replaced = True
            action = "updated"
        else:
            updated.append(entry)

    if not replaced:
        updated.append(new_entry)

    return updated, action


def update_result_rows(rows: list[ResultRow], new_rows: list[ResultRow]) -> list[ResultRow]:
    by_problem = {row.problem_id: row for row in rows}
    for row in new_rows:
        by_problem[row.problem_id] = row
    return list(by_problem.values())


def parse_result_arg(raw: str) -> ResultRow:
    parts = raw.split(":", 2)
    if len(parts) != 3:
        raise ReadmeUpdateError("--result must use PROBLEM_ID:WRONG_ATTEMPTS:ACCEPTED_SECONDS_OR_TIME")
    return ResultRow(
        problem_id=normalize_problem_id(parts[0]),
        wrong_attempts=normalize_wrong_attempts(parts[1]),
        accepted_at_seconds=normalize_accepted_seconds(parts[2]),
    )


def results_from_payload(payload: dict[str, Any]) -> list[ResultRow]:
    if payload.get("participated") is False:
        return []

    problems = payload.get("problems")
    if not isinstance(problems, list):
        raise ReadmeUpdateError("results JSON must contain a problems list.")

    result_rows: list[ResultRow] = []
    for problem in problems:
        if not isinstance(problem, dict):
            continue
        problem_id = problem.get("problem_id")
        if not isinstance(problem_id, str):
            continue
        result_rows.append(
            ResultRow(
                problem_id=normalize_problem_id(problem_id),
                wrong_attempts=normalize_wrong_attempts(problem.get("wrong_attempts", 0)),
                accepted_at_seconds=normalize_accepted_seconds(problem.get("accepted_at_seconds")),
            )
        )
    return result_rows


def load_results_json(path: Path) -> list[ResultRow]:
    if str(path) == "-":
        text = sys.stdin.read()
    else:
        text = path.expanduser().read_text(encoding="utf-8")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReadmeUpdateError(f"invalid results JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReadmeUpdateError("results JSON must be an object.")
    return results_from_payload(payload)


def collect_result_rows(args: argparse.Namespace) -> list[ResultRow]:
    rows: list[ResultRow] = []
    if args.results_json:
        rows.extend(load_results_json(args.results_json))
    for raw in args.result or []:
        rows.append(parse_result_arg(raw))
    return rows


def update_readme(args: argparse.Namespace) -> int:
    readme_path = args.readme
    if readme_path is None:
        if args.contest_dir is None:
            raise ReadmeUpdateError("pass --readme or --contest-dir.")
        readme_path = args.contest_dir / "README.md"

    readme_path = readme_path.expanduser().resolve()
    expected_header = f"# {args.contest_url.strip()}"
    new_entry = Entry(
        problem_id=normalize_problem_id(args.problem_id),
        rating=normalize_rating(args.rating),
        tags=normalize_tags(args.tags, args.tag),
    )
    new_result_rows = collect_result_rows(args)

    existing_header, entries, result_rows, unknown_lines = read_existing(readme_path)
    if existing_header and existing_header != expected_header:
        if not args.force_header:
            raise ReadmeUpdateError(
                "README header differs from the requested contest URL. "
                "Pass --force-header to replace it."
            )

    if unknown_lines and not args.force_rewrite:
        raise ReadmeUpdateError(
            "README contains unrecognized non-entry lines. "
            "Pass --force-rewrite to normalize it.\n"
            + "\n".join(f"  {line}" for line in unknown_lines[:5])
        )

    updated_entries, action = update_entries(entries, new_entry)
    updated_result_rows = update_result_rows(result_rows, new_result_rows)
    rendered = render_readme(expected_header, updated_entries, updated_result_rows)
    old_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    changed = old_text != rendered

    result = {
        "readme": str(readme_path),
        "action": action if changed else "unchanged",
        "problem_id": new_entry.problem_id,
        "entry": new_entry.line(),
        "result_rows": [
            {
                "problem_id": row.problem_id,
                "wrong_attempts": row.wrong_attempts,
                "accepted_at_seconds": row.accepted_at_seconds,
                "accepted_at": format_accepted_time(row.accepted_at_seconds),
            }
            for row in sorted(updated_result_rows, key=lambda item: problem_sort_key(item.problem_id))
        ],
        "changed": changed,
    }

    if args.dry_run:
        result["content"] = rendered
    elif changed:
        readme_path.parent.mkdir(parents=True, exist_ok=True)
        readme_path.write_text(rendered, encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['action']}: {readme_path}")
        print(new_entry.line())
        if args.dry_run:
            print()
            print(rendered, end="")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or update AtCoder/Codeforces contest README entries."
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--readme", type=Path, help="Path to README.md.")
    target.add_argument(
        "--contest-dir",
        type=Path,
        help="Contest directory. README.md will be created or updated inside it.",
    )
    parser.add_argument("--contest-url", required=True, help="Contest URL for the header.")
    parser.add_argument("--problem-id", required=True, help="Problem label, for example A or Ex.")
    parser.add_argument(
        "--rating",
        help="Rating value. Use '-' or omit for $-$. Values like 800 or $800$ are accepted.",
    )
    parser.add_argument("--tags", help="Comma-separated README tags.")
    parser.add_argument("--tag", action="append", help="One README tag. Can be repeated.")
    parser.add_argument(
        "--results-json",
        type=Path,
        help="Normalized contest result JSON from scripts/api/atcoder_results.py or scripts/api/codeforces_results.py. Use '-' for stdin.",
    )
    parser.add_argument(
        "--result",
        action="append",
        help="One result row as PROBLEM_ID:WRONG_ATTEMPTS:ACCEPTED_SECONDS_OR_TIME. Use '-' for unsolved AC time.",
    )
    parser.add_argument(
        "--force-header",
        action="store_true",
        help="Replace an existing different README header.",
    )
    parser.add_argument(
        "--force-rewrite",
        action="store_true",
        help="Drop unrecognized non-entry lines and rewrite README in the standard format.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the result without writing.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return update_readme(args)
    except ReadmeUpdateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
