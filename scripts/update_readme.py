#!/usr/bin/env python3
"""Create or update contest README entries for CP publish workflows."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ENTRY_RE = re.compile(r"^(\S+)\s*/\s*Rating\s*:\s*(.*?)\s*/\s*(.+?)\s*$")


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


def normalize_tags(raw_tags: str | None, repeated_tags: list[str] | None) -> str:
    tags: list[str] = []

    if raw_tags:
        tags.extend(part.strip() for part in raw_tags.split(","))
    if repeated_tags:
        tags.extend(part.strip() for part in repeated_tags)

    tags = [tag for tag in tags if tag]
    if not tags:
        raise ReadmeUpdateError("at least one tag is required.")

    return ", ".join(tags)


def parse_entry(line: str) -> Entry | None:
    match = ENTRY_RE.match(line)
    if not match:
        return None
    return Entry(
        problem_id=normalize_problem_id(match.group(1)),
        rating=normalize_rating(match.group(2)),
        tags=normalize_tags(match.group(3), None),
    )


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


def read_existing(readme_path: Path) -> tuple[str | None, list[Entry], list[str]]:
    if not readme_path.exists():
        return None, [], []

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None, [], []

    header = lines[0].strip()
    entries: list[Entry] = []
    unknown_lines: list[str] = []

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue

        entry = parse_entry(stripped)
        if entry is None:
            unknown_lines.append(stripped)
        else:
            entries.append(entry)

    return header, entries, unknown_lines


def render_readme(header: str, entries: list[Entry]) -> str:
    lines = [header, ""]
    for index, entry in enumerate(sorted(entries, key=lambda item: problem_sort_key(item.problem_id))):
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

    existing_header, entries, unknown_lines = read_existing(readme_path)
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
    rendered = render_readme(expected_header, updated_entries)
    old_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    changed = old_text != rendered

    result = {
        "readme": str(readme_path),
        "action": action if changed else "unchanged",
        "problem_id": new_entry.problem_id,
        "entry": new_entry.line(),
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
