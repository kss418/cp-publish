#!/usr/bin/env python3
"""Configure platform-to-repository routing for CP publishing."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ALLOWED_PLATFORMS = ("atcoder", "codeforces")
INIT_PLATFORM_CHOICES = (*ALLOWED_PLATFORMS, "both")
CONFIG_ENV = "CP_PUBLISH_CONFIG"
CONFIG_VERSION = 1
REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ConfigError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def default_config_path() -> Path:
    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override).expanduser().resolve()

    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "cp-publish" / "config.json"

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config_home).expanduser() if xdg_config_home else Path.home() / ".config"
    return base / "cp-publish" / "config.json"


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def normalize_repo_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def normalize_base_dir(value: str) -> str:
    base_dir = value.strip() or "."
    path = Path(base_dir)
    if path.is_absolute():
        raise ConfigError(f"base_dir must be relative, got: {value}")

    normalized = path.as_posix()
    if normalized in ("", "."):
        return "."

    parts = Path(normalized).parts
    if ".." in parts:
        raise ConfigError(f"base_dir must not contain '..', got: {value}")

    return normalized.rstrip("/")


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return left == right


def build_config(
    *,
    platforms: list[str],
    atcoder_repo: Path | None,
    codeforces_repo: Path | None,
    atcoder_base_dir: str | None,
    codeforces_base_dir: str | None,
) -> dict[str, Any]:
    repositories: dict[str, dict[str, str]] = {}
    routes: dict[str, dict[str, str]] = {}

    configure_atcoder = "atcoder" in platforms
    configure_codeforces = "codeforces" in platforms

    if configure_atcoder and atcoder_repo is None:
        raise ConfigError("AtCoder repository path is required.")
    if configure_codeforces and codeforces_repo is None:
        raise ConfigError("Codeforces repository path is required.")

    if (
        configure_atcoder
        and configure_codeforces
        and atcoder_repo is not None
        and codeforces_repo is not None
        and same_path(atcoder_repo, codeforces_repo)
    ):
        repositories["cp"] = {"path": str(atcoder_repo)}
        routes["atcoder"] = {
            "repo": "cp",
            "base_dir": normalize_base_dir(atcoder_base_dir or "atcoder"),
        }
        routes["codeforces"] = {
            "repo": "cp",
            "base_dir": normalize_base_dir(codeforces_base_dir or "codeforces"),
        }
    else:
        if configure_atcoder and atcoder_repo is not None:
            repositories["atcoder"] = {"path": str(atcoder_repo)}
            routes["atcoder"] = {
                "repo": "atcoder",
                "base_dir": normalize_base_dir(atcoder_base_dir or "."),
            }
        if configure_codeforces and codeforces_repo is not None:
            repositories["codeforces"] = {"path": str(codeforces_repo)}
            routes["codeforces"] = {
                "repo": "codeforces",
                "base_dir": normalize_base_dir(codeforces_base_dir or "."),
            }

    return {
        "version": CONFIG_VERSION,
        "repositories": repositories,
        "routes": routes,
    }


def read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(
            f"No cp-publish config found at {path}. Run `configure_repos.py init` first."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in config: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("Config must be a JSON object.")
    return data


def write_config(path: Path, data: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        raise ConfigError(f"Config already exists at {path}; pass --force to overwrite.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def prompt_path(label: str, *, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    if not value and default is not None:
        return default
    return value


def init_config(args: argparse.Namespace, config_path: Path) -> None:
    platforms = selected_platforms(args.platform)
    atcoder_repo = args.atcoder_repo
    codeforces_repo = args.codeforces_repo
    atcoder_base_dir = args.atcoder_base_dir
    codeforces_base_dir = args.codeforces_base_dir

    if "atcoder" in platforms and not atcoder_repo:
        atcoder_repo = prompt_path("AtCoder target repository path")
    if "atcoder" in platforms and not atcoder_repo:
        raise ConfigError("AtCoder repository path is required.")

    if "codeforces" in platforms and not codeforces_repo:
        default = atcoder_repo if "atcoder" in platforms else None
        codeforces_repo = prompt_path(
            "Codeforces target repository path", default=default
        )
    if "codeforces" in platforms and not codeforces_repo:
        raise ConfigError("Codeforces repository path is required.")

    same_repo = (
        "atcoder" in platforms
        and "codeforces" in platforms
        and atcoder_repo is not None
        and codeforces_repo is not None
        and normalize_repo_path(atcoder_repo) == normalize_repo_path(codeforces_repo)
    )

    if "atcoder" in platforms and atcoder_base_dir is None:
        default = "atcoder" if same_repo else "."
        atcoder_base_dir = prompt_path("AtCoder base directory inside repo", default=default)
    if "codeforces" in platforms and codeforces_base_dir is None:
        default = "codeforces" if same_repo else "."
        codeforces_base_dir = prompt_path(
            "Codeforces base directory inside repo", default=default
        )

    data = build_config(
        platforms=platforms,
        atcoder_repo=normalize_repo_path(atcoder_repo) if atcoder_repo else None,
        codeforces_repo=normalize_repo_path(codeforces_repo) if codeforces_repo else None,
        atcoder_base_dir=atcoder_base_dir,
        codeforces_base_dir=codeforces_base_dir,
    )
    write_config(config_path, data, force=args.force)
    print(f"wrote: {config_path}")
    print_summary(data, config_path=config_path)


def selected_platforms(value: str) -> list[str]:
    if value == "both":
        return list(ALLOWED_PLATFORMS)
    if value in ALLOWED_PLATFORMS:
        return [value]
    raise ConfigError(f"unsupported platform: {value}")


def validate_config(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("version") != CONFIG_VERSION:
        errors.append(f"version must be {CONFIG_VERSION}")

    repositories = data.get("repositories")
    routes = data.get("routes")
    if not isinstance(repositories, dict) or not repositories:
        errors.append("repositories must be a non-empty object")
        repositories = {}
    if not isinstance(routes, dict):
        errors.append("routes must be an object")
        routes = {}

    route_names = set(routes.keys())
    allowed = set(ALLOWED_PLATFORMS)
    if not route_names:
        errors.append("routes must contain at least one platform route")
    for unknown in sorted(route_names - allowed):
        errors.append(f"unsupported platform route: {unknown}")

    for repo_name, repo_info in repositories.items():
        if not isinstance(repo_name, str) or not REPO_NAME_RE.match(repo_name):
            errors.append(f"invalid repository name: {repo_name}")
            continue
        if not isinstance(repo_info, dict):
            errors.append(f"repository {repo_name} must be an object")
            continue

        repo_path_value = repo_info.get("path")
        if not isinstance(repo_path_value, str) or not repo_path_value.strip():
            errors.append(f"repository {repo_name} needs a path")
            continue

        repo_path = normalize_repo_path(repo_path_value)
        if not repo_path.exists():
            errors.append(f"repository {repo_name} path does not exist: {repo_path}")
            continue
        if not repo_path.is_dir():
            errors.append(f"repository {repo_name} path is not a directory: {repo_path}")
            continue

        root_result = run_git(["rev-parse", "--show-toplevel"], cwd=repo_path)
        if root_result.returncode != 0:
            errors.append(f"repository {repo_name} is not a git repository: {repo_path}")
            continue

        git_root = Path(root_result.stdout.strip()).resolve()
        if git_root != repo_path:
            errors.append(
                f"repository {repo_name} path must be the git root: {repo_path} (root is {git_root})"
            )

        remote_result = run_git(["remote", "get-url", "origin"], cwd=repo_path)
        if remote_result.returncode != 0:
            warnings.append(f"repository {repo_name} has no origin remote")
        else:
            remote = remote_result.stdout.strip()
            if "github.com" not in remote:
                warnings.append(
                    f"repository {repo_name} origin does not look like GitHub: {remote}"
                )

    for platform_name in sorted(route_names & allowed):
        route = routes.get(platform_name)
        if not isinstance(route, dict):
            errors.append(f"route {platform_name} must be an object")
            continue

        repo_name = route.get("repo")
        base_dir = route.get("base_dir", ".")
        if not isinstance(repo_name, str):
            errors.append(f"route {platform_name} needs a repo name")
            continue
        if repo_name not in repositories:
            errors.append(f"route {platform_name} references unknown repo: {repo_name}")
            continue
        if not isinstance(base_dir, str):
            errors.append(f"route {platform_name} base_dir must be a string")
            continue

        try:
            normalized_base_dir = normalize_base_dir(base_dir)
        except ConfigError as exc:
            errors.append(f"route {platform_name}: {exc}")
            continue

        repo_path_value = repositories[repo_name].get("path")
        if not isinstance(repo_path_value, str):
            continue
        repo_path = normalize_repo_path(repo_path_value)
        target_dir = (repo_path / normalized_base_dir).resolve()
        if target_dir != repo_path and repo_path not in target_dir.parents:
            errors.append(
                f"route {platform_name} base_dir escapes repo: {normalized_base_dir}"
            )
        elif not target_dir.exists():
            warnings.append(
                f"route {platform_name} base_dir does not exist yet: {target_dir}"
            )

    return errors, warnings


def print_summary(data: dict[str, Any], *, config_path: Path) -> None:
    print(f"config: {config_path}")
    print("repositories:")
    for name, repo in data.get("repositories", {}).items():
        print(f"  {name}: {repo.get('path')}")
    print("routes:")
    for platform_name in ALLOWED_PLATFORMS:
        route = data.get("routes", {}).get(platform_name, {})
        if not route:
            print(f"  {platform_name}: (not configured)")
            continue
        print(
            f"  {platform_name}: repo={route.get('repo')} base_dir={route.get('base_dir', '.')}"
        )


def show_config(args: argparse.Namespace, config_path: Path) -> None:
    data = read_config(config_path)
    errors, warnings = validate_config(data)

    if args.json:
        print(
            json.dumps(
                {
                    "config_path": str(config_path),
                    "config": data,
                    "valid": not errors,
                    "errors": errors,
                    "warnings": warnings,
                },
                indent=2,
            )
        )
        return

    print_summary(data, config_path=config_path)
    print_validation(errors, warnings)


def print_validation(errors: list[str], warnings: list[str]) -> None:
    if errors:
        print("errors:")
        for error in errors:
            print(f"  - {error}")
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    if not errors and not warnings:
        print("validation: ok")
    elif not errors:
        print("validation: ok with warnings")
    else:
        print("validation: failed")


def validate_command(args: argparse.Namespace, config_path: Path) -> int:
    data = read_config(config_path)
    errors, warnings = validate_config(data)

    if args.json:
        print(
            json.dumps(
                {
                    "config_path": str(config_path),
                    "valid": not errors,
                    "errors": errors,
                    "warnings": warnings,
                },
                indent=2,
            )
        )
    else:
        print(f"config: {config_path}")
        print_validation(errors, warnings)

    return 1 if errors else 0


def resolve_platform(args: argparse.Namespace, config_path: Path) -> int:
    data = read_config(config_path)
    errors, warnings = validate_config(data)
    if errors:
        raise ConfigError("Config is invalid; run `configure_repos.py validate`.")
    if args.platform not in data["routes"]:
        raise ConfigError(
            f"No route configured for {args.platform}. Run `configure_repos.py init --platform {args.platform}`."
        )

    route = data["routes"][args.platform]
    repo = data["repositories"][route["repo"]]
    repo_path = normalize_repo_path(repo["path"])
    base_dir = normalize_base_dir(route.get("base_dir", "."))
    target_base = (repo_path / base_dir).resolve()
    result = {
        "platform": args.platform,
        "repo": route["repo"],
        "repo_path": str(repo_path),
        "base_dir": base_dir,
        "target_base": str(target_base),
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"platform: {result['platform']}")
        print(f"repo: {result['repo']}")
        print(f"repo_path: {result['repo_path']}")
        print(f"base_dir: {result['base_dir']}")
        print(f"target_base: {result['target_base']}")
        if warnings:
            print("warnings:")
            for warning in warnings:
                print(f"  - {warning}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configure AtCoder/Codeforces repository routing for cp-publish."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Config path. Defaults to ${CONFIG_ENV} or the user config directory.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("path", help="Print the config file path.")

    init_parser = subparsers.add_parser("init", help="Create repository routing config.")
    init_parser.add_argument(
        "--platform",
        choices=INIT_PLATFORM_CHOICES,
        default="both",
        help="Platform route(s) to configure. Defaults to both.",
    )
    init_parser.add_argument("--atcoder-repo", help="AtCoder target git repository path.")
    init_parser.add_argument(
        "--codeforces-repo",
        help="Codeforces target git repository path. Defaults to the AtCoder repo interactively.",
    )
    init_parser.add_argument(
        "--atcoder-base-dir",
        default=None,
        help="AtCoder base directory inside its repo. Use '.' for repo root.",
    )
    init_parser.add_argument(
        "--codeforces-base-dir",
        default=None,
        help="Codeforces base directory inside its repo. Use '.' for repo root.",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite config.")

    show_parser = subparsers.add_parser("show", help="Show repository routing config.")
    show_parser.add_argument("--json", action="store_true", help="Print JSON.")

    validate_parser = subparsers.add_parser("validate", help="Validate config.")
    validate_parser.add_argument("--json", action="store_true", help="Print JSON.")

    resolve_parser = subparsers.add_parser("resolve", help="Resolve a platform route.")
    resolve_parser.add_argument("platform", choices=ALLOWED_PLATFORMS)
    resolve_parser.add_argument("--json", action="store_true", help="Print JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = args.config.expanduser().resolve() if args.config else default_config_path()

    try:
        if args.command == "path":
            print(config_path)
            return 0
        if args.command == "init":
            init_config(args, config_path)
            return 0
        if args.command == "show":
            show_config(args, config_path)
            return 0
        if args.command == "validate":
            return validate_command(args, config_path)
        if args.command == "resolve":
            return resolve_platform(args, config_path)

        parser.error(f"Unknown command: {args.command}")
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
