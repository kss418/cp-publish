from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from .config import load_route
from .detection import apply_overrides, detect_solution
from .metadata import (
    atcoder_problem_title,
    atcoder_rating,
    classify_codeforces_contest,
    codeforces_problem_title,
    codeforces_rating,
    load_atcoder_metadata,
    load_codeforces_metadata,
    resolve_codeforces_detection_by_round,
)
from .models import (
    CodeforcesTarget,
    Detection,
    PlanError,
    Route,
    SOURCE_EXTENSIONS,
    SUPPORTED_PLATFORMS,
    WEAK_FILE_STEMS,
)
from .paths import (
    build_atcoder_target,
    build_codeforces_target,
    normalize_atcoder_problem_id,
    normalize_codeforces_problem_id,
    normalize_ext,
    parse_additional_target,
    rating_markdown,
    resolve_codeforces_contest_group,
    resolve_codeforces_round_number,
)
from .tags import collect_tags


JAVA_PUBLIC_CLASS_RE = re.compile(r"\bpublic\s+class\s+([A-Za-z_$][A-Za-z0-9_$]*)\b")


def script_path(script_name: str) -> Path:
    scripts_dir = Path(__file__).resolve().parents[1]
    if script_name.startswith("api/"):
        return scripts_dir / script_name
    return Path(__file__).resolve().parent / script_name


def build_update_command(update: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        str(script_path("update_readme.py")),
        "--readme",
        update["readme"],
        "--contest-url",
        update["contest_url"],
        "--problem-id",
        update["problem_id"],
        "--rating",
        update["rating"],
    ]
    tags = update.get("tags")
    if tags:
        command.extend(["--tags", tags])
    return command


def build_contest_result_command(platform: str, contest_id: str, user_id: str | None) -> list[str] | None:
    if not user_id:
        return None
    script_name = "api/atcoder_results.py" if platform == "atcoder" else "api/codeforces_results.py"
    return [
        sys.executable,
        str(script_path(script_name)),
        "contest",
        "--contest-id",
        contest_id,
        "--user",
        user_id,
    ]


def title_from_detection_or_metadata(
    detection: Detection, metadata_title: str | None
) -> str | None:
    filename_suffix_title = any(
        evidence.startswith("Filename title suffix:") for evidence in detection.evidence
    )
    if filename_suffix_title and metadata_title:
        return metadata_title
    return detection.problem_title or metadata_title


def make_readme_update(
    contest_dir: Path,
    contest_url: str,
    problem_id: str,
    rating: str,
    tags: str | None,
    *,
    platform: str,
    contest_id: str,
    user_id: str | None,
) -> dict[str, Any]:
    update = {
        "readme": str(contest_dir / "README.md"),
        "contest_url": contest_url,
        "problem_id": problem_id,
        "rating": rating,
        "tags": tags,
        "user_id": user_id,
        "contest_result_command": build_contest_result_command(platform, contest_id, user_id),
    }
    update["command"] = build_update_command(update)
    return update


def plan_atcoder(
    source: Path,
    detection: Detection,
    route: Route,
    args: argparse.Namespace,
    warnings: list[str],
) -> dict[str, Any]:
    if not detection.contest_id or not detection.problem_id:
        raise PlanError("AtCoder planning requires contest_id and problem_id.")

    metadata = load_atcoder_metadata(args.no_metadata, args.refresh_metadata, warnings)
    task_problem_id = f"{detection.contest_id.lower()}_{detection.problem_id.lower()}"
    problem_title = title_from_detection_or_metadata(
        detection, atcoder_problem_title(task_problem_id, metadata)
    )
    rating = rating_markdown(args.rating) if args.rating else atcoder_rating(task_problem_id, metadata)
    ext = normalize_ext(source)
    target = build_atcoder_target(
        route=route,
        contest_id=detection.contest_id,
        problem_id=detection.problem_id,
        problem_title=problem_title,
        ext=ext,
        warnings=warnings,
    )
    contest_url = f"https://atcoder.jp/contests/{detection.contest_id.lower()}"
    tags = collect_tags(args)
    readme_update = make_readme_update(
        contest_dir=target.parent,
        contest_url=contest_url,
        problem_id=normalize_atcoder_problem_id(detection.problem_id),
        rating=rating,
        tags=tags,
        platform="atcoder",
        contest_id=detection.contest_id.lower(),
        user_id=route.user_id,
    )

    return {
        "targets": [str(target)],
        "readme_updates": [readme_update],
        "commit_message": f"Add AtCoder {detection.contest_id.upper()} {normalize_atcoder_problem_id(detection.problem_id)} solution",
        "metadata": {
            "contest_url": contest_url,
            "contest_id": detection.contest_id.lower(),
            "problem_id": normalize_atcoder_problem_id(detection.problem_id),
            "problem_title": problem_title,
            "rating": rating,
            "user_id": route.user_id,
        },
    }


def plan_codeforces(
    source: Path,
    detection: Detection,
    route: Route,
    args: argparse.Namespace,
    warnings: list[str],
) -> dict[str, Any]:
    if not detection.contest_id or not detection.problem_id:
        raise PlanError("Codeforces planning requires contest_id and problem_id.")

    metadata = load_codeforces_metadata(args.no_metadata, args.refresh_metadata, warnings)
    main_kind, main_title = classify_codeforces_contest(
        detection.contest_id,
        detection.contest_kind,
        detection.contest_title,
        metadata,
        warnings,
    )
    main_target = CodeforcesTarget(
        contest_id=detection.contest_id,
        problem_id=detection.problem_id,
        contest_kind=main_kind,
        contest_title=main_title,
        round_number=args.round_number or detection.round_number,
        contest_group=args.contest_group or detection.contest_group,
    )
    targets = [main_target]
    for raw in args.additional_target:
        additional = parse_additional_target(raw, main_kind)
        if not additional.contest_kind:
            additional.contest_kind, additional.contest_title = classify_codeforces_contest(
                additional.contest_id,
                None,
                None,
                metadata,
                warnings,
            )
        targets.append(additional)

    ext = normalize_ext(source)
    tags = collect_tags(args)
    target_paths: list[str] = []
    readme_updates: list[dict[str, Any]] = []
    target_metadata: list[dict[str, Any]] = []
    readme_urls_by_dir: dict[str, str] = {}
    readme_url_warnings: set[str] = set()

    for target in targets:
        if not target.contest_kind:
            warnings.append(f"Codeforces contest kind is required for contest {target.contest_id}.")
            target.contest_kind = "regular"
        problem_title = title_from_detection_or_metadata(
            detection,
            codeforces_problem_title(
                target.contest_id,
                target.problem_id,
                metadata,
            ),
        )
        target_path = build_codeforces_target(route, target, problem_title, ext, warnings)
        contest_url = f"https://codeforces.com/contest/{target.contest_id}"
        contest_dir_key = str(target_path.parent)
        readme_url = readme_urls_by_dir.setdefault(contest_dir_key, contest_url)
        if readme_url != contest_url and contest_dir_key not in readme_url_warnings:
            warnings.append(
                f"Multiple Codeforces contest IDs share README {target_path.parent / 'README.md'}; "
                f"using {readme_url} as the header."
            )
            readme_url_warnings.add(contest_dir_key)
        rating = rating_markdown(args.rating) if args.rating else codeforces_rating(
            target.contest_id,
            target.problem_id,
            metadata,
        )
        target_paths.append(str(target_path))
        readme_updates.append(
            make_readme_update(
                contest_dir=target_path.parent,
                contest_url=readme_url,
                problem_id=normalize_codeforces_problem_id(target.problem_id),
                rating=rating,
                tags=tags,
                platform="codeforces",
                contest_id=target.contest_id,
                user_id=route.user_id,
            )
        )
        target_metadata.append(
            {
                "contest_url": contest_url,
                "contest_id": target.contest_id,
                "round_number": resolve_codeforces_round_number(target),
                "contest_group": resolve_codeforces_contest_group(target),
                "contest_kind": target.contest_kind,
                "contest_title": target.contest_title,
                "problem_id": normalize_codeforces_problem_id(target.problem_id),
                "problem_title": problem_title,
                "rating": rating,
                "user_id": route.user_id,
            }
        )

    return {
        "targets": target_paths,
        "readme_updates": readme_updates,
        "commit_message": f"Add Codeforces {resolve_codeforces_round_number(main_target)}{normalize_codeforces_problem_id(detection.problem_id)} solution",
        "metadata": {
            "problem_title": target_metadata[0].get("problem_title") if target_metadata else None,
            "targets": target_metadata,
        },
    }


def source_is_weak(source: Path, detection: Detection) -> bool:
    if detection.confidence in {"none", "low"}:
        return True
    if detection.confidence == "high":
        return False
    return source.stem.lower() in WEAK_FILE_STEMS and not any(
        "path convention" in evidence.lower() for evidence in detection.evidence
    )


def check_target_conflicts(targets: list[str], warnings: list[str]) -> bool:
    needs_confirmation = False
    for target in targets:
        if Path(target).exists():
            warnings.append(f"Target already exists: {target}")
            needs_confirmation = True
    return needs_confirmation


def java_public_class_rename_warning(source: Path, targets: list[str]) -> str | None:
    if normalize_ext(source) != ".java":
        return None
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Java source could not be inspected for public class rename risk: {exc}"

    public_classes = sorted(set(JAVA_PUBLIC_CLASS_RE.findall(text)))
    if not public_classes:
        return None

    target_stems = {Path(target).stem for target in targets}
    mismatched = [name for name in public_classes if name not in target_stems]
    if not mismatched:
        return None

    classes = ", ".join(mismatched)
    stems = ", ".join(sorted(target_stems))
    return (
        f"Java source declares public class {classes}, but planned target filename stem(s) are {stems}. "
        "Java solutions with `public class Main` may not compile after renaming. "
        "Use non-public `class Main`, or publish Java solutions manually."
    )


def build_plan(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    source = Path(args.source).expanduser().resolve()
    warnings: list[str] = []

    if not source.exists():
        raise PlanError(f"Source file does not exist: {source}")
    if not source.is_file():
        raise PlanError(f"Source path is not a file: {source}")

    ext = normalize_ext(source)
    unknown_extension = ext not in SOURCE_EXTENSIONS
    if unknown_extension:
        warnings.append(f"Source extension is not a known solution language: {source.suffix}")

    detection = apply_overrides(detect_solution(source), args)
    if not detection.platform:
        raise PlanError("Could not detect platform. Pass --platform atcoder|codeforces.")
    detection.platform = detection.platform.lower()
    if detection.platform not in SUPPORTED_PLATFORMS:
        raise PlanError(f"Unsupported platform: {detection.platform}")
    if detection.platform == "codeforces" and not detection.contest_id and detection.round_number:
        metadata = load_codeforces_metadata(args.no_metadata, args.refresh_metadata, warnings)
        resolve_codeforces_detection_by_round(detection, metadata, warnings)
    if not detection.contest_id or not detection.problem_id:
        raise PlanError("Could not detect contest/problem. Pass --contest-id and --problem-id.")

    route = load_route(detection.platform, args.config)
    warnings.extend(route.warnings)
    if not route.user_id:
        user_warning = (
            f"{detection.platform} user id is not configured; ask the user and run "
            f"`scripts/init/configure_repos.py user {detection.platform} --id <id>` before adding contest results to README."
        )
        if not any("user id" in warning and detection.platform in warning for warning in warnings):
            warnings.append(user_warning)

    if detection.platform == "atcoder":
        platform_plan = plan_atcoder(source, detection, route, args, warnings)
    else:
        platform_plan = plan_codeforces(source, detection, route, args, warnings)

    java_warning = java_public_class_rename_warning(source, platform_plan["targets"])
    if java_warning:
        warnings.append(java_warning)

    needs_confirmation = False
    if unknown_extension:
        needs_confirmation = True
    if java_warning:
        needs_confirmation = True
    if source_is_weak(source, detection):
        warnings.append("Problem identity is based on weak evidence; confirm before publishing.")
        needs_confirmation = True
    if any(item.startswith("CLI override changed ") for item in detection.evidence):
        warnings.append("CLI overrides conflict with detected source metadata; confirm before publishing.")
        needs_confirmation = True
    if detection.conflicts:
        warnings.extend(detection.conflicts)
        needs_confirmation = True
    if not collect_tags(args):
        warnings.append("README tags were not provided; infer tags from the solution code before updating README.")
        needs_confirmation = True
    if any("required" in warning.lower() or "ambiguous" in warning.lower() for warning in warnings):
        needs_confirmation = True
    if not route.user_id:
        needs_confirmation = True
    if check_target_conflicts(platform_plan["targets"], warnings):
        needs_confirmation = True

    plan = {
        "source": str(source),
        "platform": detection.platform,
        "repo": str(route.repo_path),
        "base_dir": route.base_dir,
        "user_id": route.user_id,
        "targets": platform_plan["targets"],
        "readme_updates": platform_plan["readme_updates"],
        "commit_message": platform_plan["commit_message"],
        "needs_confirmation": needs_confirmation,
        "detection": {
            "contest_id": detection.contest_id,
            "problem_id": detection.problem_id,
            "problem_title": platform_plan["metadata"].get("problem_title"),
            "contest_kind": detection.contest_kind,
            "contest_title": detection.contest_title,
            "round_number": detection.round_number,
            "contest_group": detection.contest_group,
            "confidence": detection.confidence,
            "evidence": detection.evidence,
            "conflicts": detection.conflicts,
        },
        "metadata": platform_plan["metadata"],
        "warnings": warnings,
    }
    return plan, 0


def make_error_plan(source: str | None, message: str) -> dict[str, Any]:
    return {
        "source": source,
        "targets": [],
        "readme_updates": [],
        "commit_message": None,
        "needs_confirmation": True,
        "errors": [message],
    }
