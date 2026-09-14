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
import tempfile
import time
import math
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cp_publish.file_io import atomic_write_text, source_sha256
from cp_publish.update_readme import ReadmeUpdateError, build_parser as readme_parser, prepare_readme_group, results_from_payload

RESULT_SNAPSHOT_MAX_AGE = 300


def valid_result_snapshots(value: Any) -> dict[tuple[str, ...], dict[str, Any]]:
    """Invalid, expired, or future-dated records fall back to the normal helper."""
    records = {}
    if not isinstance(value, list):
        return records
    now = time.time()
    for item in value:
        if not isinstance(item, dict):
            continue
        command, fetched_at, payload = item.get("command"), item.get("fetched_at"), item.get("payload")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
            continue
        if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)) or not math.isfinite(fetched_at):
            continue
        if not 0 <= now - fetched_at < RESULT_SNAPSHOT_MAX_AGE or not isinstance(payload, dict):
            continue
        try:
            results_from_payload(payload)
        except (ReadmeUpdateError, TypeError, ValueError, OverflowError):
            continue
        records[tuple(command)] = item
    return records


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


def validate_source_fingerprint(plan: dict[str, Any], source: Path) -> None:
    expected = plan.get("source_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ApplyPlanError("Plan has no valid source SHA-256; rebuild the plan before applying.")
    try:
        actual = source_sha256(source)
    except OSError as exc:
        raise ApplyPlanError(f"Could not hash source: {source}: {exc}") from exc
    if actual != expected:
        raise ApplyPlanError(f"Source changed since planning; rebuild the plan: {source}")


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


def skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


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
            actions.append(
                {
                    "path": str(target),
                    "changed": False,
                    "operation": "move" if move else "copy",
                    "already_at_target": True,
                }
            )
            continue
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
    results_json = update.get("_results_json")
    if isinstance(results_json, str) and results_json:
        command.extend(["--results-json", results_json])
    if dry_run:
        command.append("--dry-run")
    return command


def normalize_command(value: Any, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ApplyPlanError(f"Plan field {field_name!r} must be a non-empty command list.")
    command: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ApplyPlanError(f"Plan field {field_name!r} must contain only non-empty strings.")
        command.append(item)
    return command


def fetch_result_json(
    *,
    command: list[str],
    temp_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    result = subprocess.run(
        command,
        cwd=str(skill_root()),
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ApplyPlanError(detail or f"result command failed with exit code {result.returncode}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ApplyPlanError(f"result command returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ApplyPlanError("result command returned a non-object JSON payload.")

    path = temp_dir / f"contest-results-{len(list(temp_dir.iterdir())) + 1}.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path, payload


def prepare_readme_updates(
    updates: list[dict[str, Any]],
    *,
    with_results: bool,
    require_results: bool,
    temp_dir: Path,
    saved_results: Any = None,
    captured_results: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    prepared_updates: list[dict[str, Any]] = []
    result_fetches: list[dict[str, Any]] = []
    warnings: list[str] = []
    cache: dict[tuple[str, ...], tuple[Path, dict[str, Any]]] = {}
    failures: dict[tuple[str, ...], str] = {}
    snapshots = valid_result_snapshots(saved_results)
    restored: set[tuple[str, ...]] = set()

    for index, update in enumerate(updates):
        prepared = dict(update)
        prepared_updates.append(prepared)

        if not with_results:
            continue

        field_name = f"readme_updates[{index}].contest_result_command"
        command = normalize_command(update.get("contest_result_command"), field_name)
        readme = str(update.get("readme", ""))
        if command is None:
            message = f"No contest result command is available for README update: {readme}"
            if require_results:
                raise ApplyPlanError(message)
            warnings.append(message)
            result_fetches.append({"readme": readme, "status": "skipped", "reason": message})
            continue

        key = tuple(command)
        reused = key in cache or key in failures
        try:
            if key in failures:
                raise ApplyPlanError(failures[key])
            if key not in cache:
                record = snapshots.get(key)
                if record is not None:
                    payload = record["payload"]
                    results_path = temp_dir / f"saved-results-{len(cache)}.json"
                    atomic_write_text(results_path, json.dumps(payload, ensure_ascii=False) + "\n")
                    cache[key] = (results_path, payload)
                    restored.add(key)
                else:
                    cache[key] = fetch_result_json(command=command, temp_dir=temp_dir)
                    record = {"command": command, "fetched_at": time.time(), "payload": cache[key][1]}
                if captured_results is not None and valid_result_snapshots([record]):
                    captured_results.append(record)
            results_path, payload = cache[key]
        except ApplyPlanError as exc:
            failures[key] = str(exc)
            message = f"Contest result fetch failed for {readme}: {exc}"
            if require_results:
                raise ApplyPlanError(message) from exc
            warnings.append(message)
            result_fetches.append(
                {
                    "readme": readme,
                    "status": "failed",
                    "command": command,
                    "error": str(exc),
                    "reused": reused,
                }
            )
            continue

        prepared["_results_json"] = str(results_path)
        problems = payload.get("problems")
        problem_count = len(problems) if isinstance(problems, list) else None
        result_fetches.append(
            {
                "readme": readme,
                "status": "ok",
                "command": command,
                "problem_count": problem_count,
                "reused": reused,
                "from_saved_plan": key in restored,
            }
        )

    return prepared_updates, result_fetches, warnings


def prepare_grouped_readmes(
    updates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[Path, str]]]:
    """Prepare all README files before any source mutation; preserve result order."""
    groups: dict[Path, list[tuple[int, argparse.Namespace]]] = {}
    parser = readme_parser()
    for index, update in enumerate(updates):
        arguments = parser.parse_args(build_update_readme_args(update, dry_run=True)[2:])
        groups.setdefault(arguments.readme.resolve(), []).append((index, arguments))
    results: list[dict[str, Any]] = [{} for _ in updates]
    writes: list[tuple[Path, str]] = []
    try:
        for path, group in groups.items():
            prepared, rendered = prepare_readme_group([args for _, args in group])
            for (index, _), result in zip(group, prepared):
                results[index] = result
            if any(result["changed"] for result in prepared):
                writes.append((path, rendered))
    except (ReadmeUpdateError, OSError) as exc:
        raise ApplyPlanError(f"README preparation failed: {exc}") from exc
    return results, writes


def write_grouped_readmes(writes: list[tuple[Path, str]]) -> None:
    for path, content in writes:
        try:
            atomic_write_text(path, content)
        except OSError as exc:
            raise ApplyPlanError(f"Could not replace README {path}: {exc}") from exc


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
        path = resolved_path(action["path"], "target")
        if action.get("already_at_target"):
            relative = relative_to_repo(path, repo)
            if relative:
                commit_paths.append(relative)
            continue
        if not action["changed"]:
            continue
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

    validate_source_fingerprint(plan, source)

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

    result_fetches: list[dict[str, Any]] = []
    warnings: list[str] = []
    with_results = not args.no_results or args.require_results

    with tempfile.TemporaryDirectory(prefix="cp-publish-results-") as temp_dir_name:
        prepared_readme_updates, result_fetches, result_warnings = prepare_readme_updates(
            readme_updates,
            with_results=with_results,
            require_results=args.require_results,
            temp_dir=Path(temp_dir_name),
        )
        warnings.extend(result_warnings)

        readme_results, readme_writes = prepare_grouped_readmes(prepared_readme_updates)
        if not args.dry_run:
            validate_source_fingerprint(plan, source)
            copy_or_move_files(
                source=source,
                file_actions=file_actions,
                move=args.move,
                overwrite=args.overwrite,
            )
            write_grouped_readmes(readme_writes)

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
                "result_rows": result.get("result_rows", []),
            }
            for result in readme_results
        ],
        "result_fetches": result_fetches,
        "warnings": warnings,
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
    parser.add_argument(
        "--with-results",
        action="store_true",
        help="Deprecated compatibility flag; contest results are fetched by default.",
    )
    parser.add_argument(
        "--no-results",
        action="store_true",
        help="Skip contest result fetches and update only solution README entries.",
    )
    parser.add_argument(
        "--require-results",
        action="store_true",
        help="Fail if default contest result fetches cannot be completed.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing target files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_results and args.require_results:
        parser.error("--no-results cannot be used with --require-results.")
    try:
        result = apply_plan(load_plan(args.plan), args)
    except ApplyPlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
