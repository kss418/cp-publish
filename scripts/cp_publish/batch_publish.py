#!/usr/bin/env python3
"""Build and apply publish plans for multiple CP solution files."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cp_publish.apply_plan import (
    ApplyPlanError,
    changed_and_commit_paths,
    copy_or_move_files,
    prepare_readme_updates,
    resolved_path,
    resolved_path_list,
    run_update_readme,
    unique,
    validate_file_targets,
    validate_readme_updates,
)
from cp_publish.models import PlanError, SOURCE_EXTENSIONS, SUPPORTED_PLATFORMS
from cp_publish.paths import (
    normalize_codeforces_contest_group,
    normalize_codeforces_kind,
    normalize_codeforces_round_number,
    normalize_ext,
)
from cp_publish.planning import build_plan, make_error_plan


README_ENTRY_RE = re.compile(
    r"^\s*([A-Za-z0-9]+)\s*/\s*Rating\s*:\s*\$[^$]*\$\s*/\s*(.+?)\s*$"
)


class BatchPublishError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def is_solution_file(path: Path) -> bool:
    return path.is_file() and normalize_ext(path) in SOURCE_EXTENSIONS


def collect_from_dir(path: Path, recursive: bool) -> list[Path]:
    iterator = path.rglob("*") if recursive else path.iterdir()
    return sorted(
        [item.resolve() for item in iterator if is_solution_file(item)],
        key=lambda item: str(item).casefold(),
    )


def collect_sources(values: list[str], from_dirs: list[str], recursive: bool) -> list[Path]:
    sources: list[Path] = []

    for raw in from_dirs:
        path = Path(raw).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise BatchPublishError(f"--from-dir is not a directory: {path}")
        sources.extend(collect_from_dir(path, recursive))

    for raw in values:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise BatchPublishError(f"Source path does not exist: {path}")
        if path.is_dir():
            sources.extend(collect_from_dir(path, recursive))
        elif path.is_file():
            sources.append(path)
        else:
            raise BatchPublishError(f"Source path is neither file nor directory: {path}")

    unique_sources = list(dict.fromkeys(sources))
    if not unique_sources:
        raise BatchPublishError("No solution files were provided or found.")
    return unique_sources


def infer_problem_id_from_filename(path: Path) -> str | None:
    token = path.stem.split("_", 1)[0].strip()
    token = token.replace("-", "").replace(" ", "")
    if not token or not re.fullmatch(r"[A-Za-z0-9]+", token):
        return None
    return token.upper()


def read_readme_tags(readme: Path) -> dict[str, str]:
    if not readme.exists() or not readme.is_file():
        return {}
    tags_by_problem: dict[str, str] = {}
    for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
        match = README_ENTRY_RE.match(line)
        if not match:
            continue
        tags_by_problem[match.group(1).upper()] = match.group(2).strip()
    return tags_by_problem


def tags_from_readme(source: Path) -> str | None:
    problem_id = infer_problem_id_from_filename(source)
    if not problem_id:
        return None
    return read_readme_tags(source.parent / "README.md").get(problem_id)


def validate_shared_overrides(args: argparse.Namespace, source_count: int) -> None:
    if source_count <= 1:
        return
    unsafe = []
    for field in ("problem_id", "problem_title", "rating"):
        if getattr(args, field):
            unsafe.append(f"--{field.replace('_', '-')}")
    if args.additional_target:
        unsafe.append("--additional-target")
    if unsafe:
        joined = ", ".join(unsafe)
        raise BatchPublishError(
            f"{joined} can only be used with a single source. "
            "For batch publishing, let each file detect its own problem metadata."
        )


def plan_args_for_source(args: argparse.Namespace, source: Path) -> argparse.Namespace:
    tags = args.tags
    if not tags and not args.tag and args.tags_from_readme:
        tags = tags_from_readme(source)

    problem_id = args.problem_id
    if not problem_id and args.problem_id_from_filename:
        problem_id = infer_problem_id_from_filename(source)

    return argparse.Namespace(
        source=str(source),
        config=args.config,
        platform=args.platform,
        contest_id=args.contest_id,
        problem_id=problem_id,
        problem_title=args.problem_title,
        contest_kind=args.contest_kind,
        contest_title=args.contest_title,
        round_number=args.round_number,
        contest_group=args.contest_group,
        additional_target=list(args.additional_target),
        rating=args.rating,
        tags=tags,
        tag=list(args.tag),
        no_metadata=args.no_metadata,
        refresh_metadata=args.refresh_metadata,
    )


def build_batch_plans(args: argparse.Namespace, sources: list[Path]) -> tuple[list[dict[str, Any]], int]:
    plans: list[dict[str, Any]] = []
    status = 0
    for source in sources:
        try:
            plan, plan_status = build_plan(plan_args_for_source(args, source))
            status = max(status, plan_status)
        except PlanError as exc:
            plan = make_error_plan(str(source), str(exc))
            status = 1
        plans.append(plan)
    return plans, status


def normalize_plan(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
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
    return {
        "plan": plan,
        "source": source,
        "repo": repo,
        "targets": targets,
        "readme_updates": readme_updates,
        "file_actions": file_actions,
    }


def ensure_batch_safe(actions: list[dict[str, Any]], *, move: bool) -> None:
    sources = [action["source"] for action in actions]
    if len(set(sources)) != len(sources):
        raise ApplyPlanError("The same source file appears more than once in the batch.")

    changed_targets: list[Path] = []
    for action in actions:
        for file_action in action["file_actions"]:
            if file_action.get("changed"):
                changed_targets.append(resolved_path(file_action["path"], "target"))
    if len(set(changed_targets)) != len(changed_targets):
        raise ApplyPlanError("Multiple plans write to the same target path.")

    if move:
        target_set = set(changed_targets)
        for source in sources:
            if source in target_set:
                raise ApplyPlanError("A moved source is also used as another plan target.")


def summarize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    detection = plan.get("detection") if isinstance(plan.get("detection"), dict) else {}
    return {
        "source": plan.get("source"),
        "platform": plan.get("platform"),
        "contest_id": detection.get("contest_id"),
        "problem_id": detection.get("problem_id"),
        "problem_title": detection.get("problem_title"),
        "targets": plan.get("targets", []),
        "needs_confirmation": bool(plan.get("needs_confirmation")),
        "warnings": plan.get("warnings", []),
        "errors": plan.get("errors", []),
    }


def suggested_commit_message(plans: list[dict[str, Any]]) -> str:
    usable = [plan for plan in plans if not plan.get("errors")]
    if len(usable) == 1:
        message = usable[0].get("commit_message")
        if isinstance(message, str) and message:
            return message

    platforms = {plan.get("platform") for plan in usable}
    if len(platforms) == 1 and "codeforces" in platforms:
        rounds: set[str] = set()
        for plan in usable:
            metadata = plan.get("metadata")
            targets = metadata.get("targets") if isinstance(metadata, dict) else None
            if isinstance(targets, list) and targets:
                round_number = targets[0].get("round_number")
                if isinstance(round_number, str) and round_number:
                    rounds.add(round_number)
        if len(rounds) == 1:
            return f"Publish Codeforces {next(iter(rounds))} solutions"
        return f"Publish {len(usable)} Codeforces solutions"

    if len(platforms) == 1 and "atcoder" in platforms:
        contests = {
            plan.get("metadata", {}).get("contest_id")
            for plan in usable
            if isinstance(plan.get("metadata"), dict)
        }
        contests.discard(None)
        if len(contests) == 1:
            return f"Publish AtCoder {next(iter(contests)).upper()} solutions"
        return f"Publish {len(usable)} AtCoder solutions"

    return f"Publish {len(usable)} competitive programming solutions"


def apply_batch(plans: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    actions = [normalize_plan(plan, args) for plan in plans]
    ensure_batch_safe(actions, move=args.move)

    all_readme_updates: list[dict[str, Any]] = []
    readme_counts: list[int] = []
    for action in actions:
        readme_counts.append(len(action["readme_updates"]))
        all_readme_updates.extend(action["readme_updates"])

    result_fetches: list[dict[str, Any]] = []
    warnings: list[str] = []
    with_results = not args.no_results or args.require_results

    with tempfile.TemporaryDirectory(prefix="cp-publish-results-") as temp_dir_name:
        prepared_updates, result_fetches, result_warnings = prepare_readme_updates(
            all_readme_updates,
            with_results=with_results,
            require_results=args.require_results,
            temp_dir=Path(temp_dir_name),
        )
        warnings.extend(result_warnings)

        readme_preflight = [run_update_readme(update, dry_run=True) for update in prepared_updates]
        if args.dry_run:
            readme_results = readme_preflight
        else:
            for action in actions:
                copy_or_move_files(
                    source=action["source"],
                    file_actions=action["file_actions"],
                    move=args.move,
                    overwrite=args.overwrite,
                )
            readme_results = [run_update_readme(update, dry_run=False) for update in prepared_updates]

    all_changed_paths: list[str] = []
    all_commit_paths: list[str] = []
    commit_paths_by_repo: dict[str, list[str]] = {}
    batch_targets: list[dict[str, Any]] = []
    batch_readme_results: list[dict[str, Any]] = []
    cursor = 0
    for action, count in zip(actions, readme_counts):
        plan_readme_results = readme_results[cursor : cursor + count]
        cursor += count
        changed_paths, commit_paths = changed_and_commit_paths(
            repo=action["repo"],
            source=action["source"],
            file_actions=action["file_actions"],
            readme_results=plan_readme_results,
            move=args.move,
        )
        all_changed_paths.extend(changed_paths)
        all_commit_paths.extend(commit_paths)
        repo_key = str(action["repo"])
        commit_paths_by_repo.setdefault(repo_key, []).extend(commit_paths)
        batch_targets.extend(action["file_actions"])
        batch_readme_results.extend(plan_readme_results)

    commit_paths = unique(all_commit_paths)
    grouped_commit_paths = {
        repo: unique(paths) for repo, paths in commit_paths_by_repo.items()
    }
    return {
        "dry_run": args.dry_run,
        "operation": "move" if args.move else "copy",
        "plan_count": len(plans),
        "plans": [summarize_plan(plan) for plan in plans],
        "targets": batch_targets,
        "readme_updates": [
            {
                "readme": result.get("readme"),
                "action": result.get("action"),
                "changed": bool(result.get("changed")),
                "problem_id": result.get("problem_id"),
                "result_rows": result.get("result_rows", []),
            }
            for result in batch_readme_results
        ],
        "result_fetches": result_fetches,
        "warnings": unique([*warnings, *[warning for plan in plans for warning in plan.get("warnings", [])]]),
        "changed_paths": unique(all_changed_paths),
        "commit_paths": commit_paths,
        "commit_paths_by_repo": grouped_commit_paths,
        "suggested_commit_message": args.commit_message or suggested_commit_message(plans),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch publish multiple CP solution files.")
    parser.add_argument("sources", nargs="*", help="Solution files or directories to publish.")
    parser.add_argument("--from-dir", action="append", default=[], help="Collect solution files from a directory.")
    parser.add_argument("--recursive", action="store_true", help="Collect solution files recursively from directories.")
    parser.add_argument("--config", help="Path to cp-publish config JSON.")
    parser.add_argument("--platform", choices=sorted(SUPPORTED_PLATFORMS), help="Override detected platform.")
    parser.add_argument("--contest-id", help="Override detected contest id.")
    parser.add_argument("--problem-id", help="Override detected problem id/index. Single-source batches only.")
    parser.add_argument("--problem-id-from-filename", action="store_true", help="Use filename prefix as problem id.")
    parser.add_argument("--problem-title", help="Override or provide the problem title. Single-source batches only.")
    parser.add_argument(
        "--contest-kind",
        metavar="{regular,Educational,Others}",
        type=normalize_codeforces_kind,
        help="Codeforces path class.",
    )
    parser.add_argument("--contest-title", help="Codeforces contest title used for path classification.")
    parser.add_argument(
        "--round-number",
        type=normalize_codeforces_round_number,
        help="Codeforces round number used for path placement.",
    )
    parser.add_argument(
        "--contest-group",
        type=normalize_codeforces_contest_group,
        help="Codeforces Others group directory name, for example Global_Round.",
    )
    parser.add_argument(
        "--additional-target",
        action="append",
        default=[],
        help="Extra Codeforces target. Single-source batches only.",
    )
    parser.add_argument("--rating", help="Override README rating. Single-source batches only.")
    parser.add_argument("--tags", help="Comma-separated README tags applied to every source.")
    parser.add_argument("--tag", action="append", default=[], help="README tag. Can be repeated or comma-separated.")
    parser.add_argument(
        "--tags-from-readme",
        action="store_true",
        help="Use each source directory's README entry tags when --tags/--tag are absent.",
    )
    parser.add_argument("--no-metadata", action="store_true", help="Do not fetch or read platform metadata.")
    parser.add_argument("--refresh-metadata", action="store_true", help="Refresh cached platform metadata if needed.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--copy", action="store_true", help="Copy each source file to its planned target.")
    action.add_argument("--move", action="store_true", help="Move each source file to its planned target.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show planned changes without writing.")
    parser.add_argument(
        "--allow-confirmation",
        action="store_true",
        help="Apply plans whose needs_confirmation field is true.",
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
    parser.add_argument("--require-results", action="store_true", help="Fail if contest results cannot be fetched.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing target files.")
    parser.add_argument("--commit-message", help="Override the suggested batch commit message.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_results and args.require_results:
        parser.error("--no-results cannot be used with --require-results.")
    try:
        sources = collect_sources(args.sources, args.from_dir, args.recursive)
        validate_shared_overrides(args, len(sources))
        plans, status = build_batch_plans(args, sources)
        if any(plan.get("errors") for plan in plans):
            result = {
                "dry_run": args.dry_run,
                "plan_count": len(plans),
                "plans": [summarize_plan(plan) for plan in plans],
                "blocked": True,
                "suggested_commit_message": args.commit_message or suggested_commit_message(plans),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        if any(plan.get("needs_confirmation") for plan in plans) and not args.allow_confirmation:
            result = {
                "dry_run": args.dry_run,
                "plan_count": len(plans),
                "plans": [summarize_plan(plan) for plan in plans],
                "blocked": True,
                "reason": "one or more plans need confirmation",
                "suggested_commit_message": args.commit_message or suggested_commit_message(plans),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        result = apply_batch(plans, args)
    except (BatchPublishError, ApplyPlanError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return getattr(exc, "returncode", 1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
