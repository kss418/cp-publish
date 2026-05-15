#!/usr/bin/env python3
"""Apply a cp-publish plan without hand-written shell file operations."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class ApplyPlanError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def script_path(script_name: str) -> Path:
    return Path(__file__).resolve().with_name(script_name)


def decode_plan_bytes(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ApplyPlanError("Could not decode plan as UTF-8 or UTF-16 JSON text.")


def load_plan(plan_path: str) -> dict[str, Any]:
    try:
        if plan_path == "-":
            payload = sys.stdin.read()
        else:
            payload = decode_plan_bytes(Path(plan_path).expanduser().read_bytes())
        plan = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise ApplyPlanError(f"Could not read plan: {exc}") from exc

    if not isinstance(plan, dict):
        raise ApplyPlanError("Plan must be a JSON object.")
    return plan


def resolved_path(value: Any, field_name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ApplyPlanError(f"Plan field {field_name!r} must be a non-empty string.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def resolved_path_list(value: Any, field_name: str) -> list[Path]:
    if not isinstance(value, list) or not value:
        raise ApplyPlanError(f"Plan field {field_name!r} must be a non-empty list.")
    return [resolved_path(item, f"{field_name}[]") for item in value]


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def require_under_repo(path: Path, repo: Path, label: str) -> None:
    if not is_under(path, repo):
        raise ApplyPlanError(f"{label} is outside the planned repo: {path}")


def relative_to_repo(path: Path, repo: Path) -> str | None:
    if not is_under(path, repo):
        return None
    return os.path.relpath(path, repo)


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def source_target_changed(source: Path, target: Path) -> bool:
    if not target.exists():
        return True
    if not target.is_file():
        raise ApplyPlanError(f"Target exists and is not a file: {target}")
    return not filecmp.cmp(source, target, shallow=False)


def validate_file_targets(
    *,
    source: Path,
    targets: list[Path],
    repo: Path,
    move: bool,
    overwrite: bool,
) -> list[dict[str, Any]]:
    if move and len(targets) != 1:
        raise ApplyPlanError("--move can only be used with a plan that has one target.")

    actions: list[dict[str, Any]] = []
    for target in targets:
        require_under_repo(target, repo, "target")
        if source == target:
            raise ApplyPlanError(f"Source and target are the same path: {source}")
        changed = source_target_changed(source, target)
        if changed and target.exists() and not overwrite:
            raise ApplyPlanError(
                "Target already exists with different content; "
                f"pass --overwrite to replace it: {target}"
            )
        actions.append(
            {
                "path": str(target),
                "changed": changed,
                "operation": "move" if move else "copy",
            }
        )
    return actions


def build_update_readme_args(update: dict[str, Any], *, dry_run: bool) -> list[str]:
    readme = update.get("readme")
    contest_url = update.get("contest_url")
    problem_id = update.get("problem_id")
    if not all(isinstance(item, str) and item for item in (readme, contest_url, problem_id)):
        raise ApplyPlanError("README update is missing readme, contest_url, or problem_id.")

    command = [
        sys.executable,
        str(script_path("update_readme.py")),
        "--readme",
        readme,
        "--contest-url",
        contest_url,
        "--problem-id",
        problem_id,
        "--json",
    ]
    rating = update.get("rating")
    if isinstance(rating, str) and rating:
        command.extend(["--rating", rating])
    tags = update.get("tags")
    if isinstance(tags, str) and tags:
        command.extend(["--tags", tags])
    if dry_run:
        command.append("--dry-run")
    return command


def run_update_readme(update: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    command = build_update_readme_args(update, dry_run=dry_run)
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ApplyPlanError(f"README update failed: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ApplyPlanError(f"README update returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ApplyPlanError("README update returned a non-object JSON payload.")
    return payload


def validate_readme_updates(updates: Any, repo: Path) -> list[dict[str, Any]]:
    if updates is None:
        return []
    if not isinstance(updates, list):
        raise ApplyPlanError("Plan field 'readme_updates' must be a list when present.")
    for update in updates:
        if not isinstance(update, dict):
            raise ApplyPlanError("Each README update must be a JSON object.")
        readme = resolved_path(update.get("readme"), "readme_updates[].readme")
        require_under_repo(readme, repo, "README")
    return updates


def copy_or_move_files(
    *,
    source: Path,
    file_actions: list[dict[str, Any]],
    move: bool,
    overwrite: bool,
) -> None:
    for action in file_actions:
        if not action["changed"]:
            continue
        target = resolved_path(action["path"], "target")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and overwrite:
            target.unlink()
        if move:
            shutil.move(str(source), str(target))
        else:
            shutil.copy2(source, target)


def changed_and_commit_paths(
    *,
    repo: Path,
    source: Path,
    file_actions: list[dict[str, Any]],
    readme_results: list[dict[str, Any]],
    move: bool,
) -> tuple[list[str], list[str]]:
    changed_paths: list[str] = []
    commit_paths: list[str] = []

    for action in file_actions:
        if not action["changed"]:
            continue
        path = resolved_path(action["path"], "target")
        changed_paths.append(str(path))
        relative = relative_to_repo(path, repo)
        if relative:
            commit_paths.append(relative)

    if move and any(action["changed"] for action in file_actions):
        changed_paths.append(str(source))
        relative = relative_to_repo(source, repo)
        if relative:
            commit_paths.append(relative)

    for result in readme_results:
        if not result.get("changed"):
            continue
        path = resolved_path(result.get("readme"), "readme")
        changed_paths.append(str(path))
        relative = relative_to_repo(path, repo)
        if relative:
            commit_paths.append(relative)

    return unique(changed_paths), unique(commit_paths)


def apply_plan(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if plan.get("errors"):
        raise ApplyPlanError("Refusing to apply an error plan: " + "; ".join(map(str, plan["errors"])))
    if plan.get("needs_confirmation") and not args.allow_confirmation:
        raise ApplyPlanError(
            "Plan needs confirmation; inspect warnings and rerun with --allow-confirmation if approved."
        )

    source = resolved_path(plan.get("source"), "source")
    if not source.exists():
        raise ApplyPlanError(f"Source file does not exist: {source}")
    if not source.is_file():
        raise ApplyPlanError(f"Source path is not a file: {source}")

    repo = resolved_path(plan.get("repo"), "repo")
    if not repo.exists() or not repo.is_dir():
        raise ApplyPlanError(f"Planned repo does not exist or is not a directory: {repo}")

    targets = resolved_path_list(plan.get("targets"), "targets")
    readme_updates = validate_readme_updates(plan.get("readme_updates", []), repo)

    file_actions = validate_file_targets(
        source=source,
        targets=targets,
        repo=repo,
        move=args.move,
        overwrite=args.overwrite,
    )

    readme_preflight = [run_update_readme(update, dry_run=True) for update in readme_updates]
    if args.dry_run:
        readme_results = readme_preflight
    else:
        copy_or_move_files(
            source=source,
            file_actions=file_actions,
            move=args.move,
            overwrite=args.overwrite,
        )
        readme_results = [run_update_readme(update, dry_run=False) for update in readme_updates]

    changed_paths, commit_paths = changed_and_commit_paths(
        repo=repo,
        source=source,
        file_actions=file_actions,
        readme_results=readme_results,
        move=args.move,
    )

    return {
        "dry_run": args.dry_run,
        "operation": "move" if args.move else "copy",
        "source": str(source),
        "targets": file_actions,
        "readme_updates": [
            {
                "readme": result.get("readme"),
                "action": result.get("action"),
                "changed": bool(result.get("changed")),
                "problem_id": result.get("problem_id"),
            }
            for result in readme_results
        ],
        "changed_paths": changed_paths,
        "commit_paths": commit_paths,
        "commit_message": plan.get("commit_message"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply a cp-publish plan.")
    parser.add_argument("--plan", required=True, help="Path to a plan JSON file, or '-' for stdin.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--copy", action="store_true", help="Copy the source file to every planned target.")
    action.add_argument("--move", action="store_true", help="Move the source file to the planned target.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show planned changes without writing.")
    parser.add_argument(
        "--allow-confirmation",
        action="store_true",
        help="Apply a plan whose needs_confirmation field is true.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing target files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = apply_plan(load_plan(args.plan), args)
    except ApplyPlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
