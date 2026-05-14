#!/usr/bin/env python3
"""Safe GitHub CLI helpers for competitive-programming publish workflows."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from check_dependencies import install_command


class CommandError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        hint = install_command(name)
        message = f"Required dependency not found on PATH: {name}"
        if hint:
            message = f"{message}\ninstall_command: {hint}"
        raise CommandError(message)


def repo_root(start: Path) -> Path:
    require_tool("git")
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=start)
    return Path(result.stdout.strip()).resolve()


def current_branch(root: Path) -> str:
    result = run(["git", "branch", "--show-current"], cwd=root)
    branch = result.stdout.strip()
    if not branch:
        raise CommandError("Detached HEAD is not supported for publishing.")
    return branch


def git_porcelain(root: Path) -> list[str]:
    result = run(["git", "status", "--porcelain"], cwd=root)
    return [line for line in result.stdout.splitlines() if line.strip()]


def upstream_ref(root: Path) -> str | None:
    result = run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=root,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def origin_url(root: Path) -> str | None:
    result = run(["git", "remote", "get-url", "origin"], cwd=root, check=False)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def gh_auth_status() -> subprocess.CompletedProcess[str]:
    require_tool("gh")
    return run(["gh", "auth", "status"], check=False)


def ensure_auth(*, login: bool, setup_git: bool) -> None:
    status = gh_auth_status()
    if status.returncode != 0:
        if not login:
            raise CommandError(
                "GitHub CLI is not authenticated. Run this command again with "
                "`auth --login`, or run `gh auth login --web` yourself."
            )
        run(["gh", "auth", "login", "--web"], check=True, capture=False)

    status = gh_auth_status()
    if status.returncode != 0:
        raise CommandError("GitHub CLI authentication still failed after login.")

    if setup_git:
        run(["gh", "auth", "setup-git"], check=True, capture=False)


def print_status(root: Path) -> None:
    print(f"repo: {root}")
    print(f"branch: {current_branch(root)}")

    remote = origin_url(root)
    print(f"origin: {remote or '(missing)'}")

    upstream = upstream_ref(root)
    print(f"upstream: {upstream or '(missing)'}")

    changes = git_porcelain(root)
    if changes:
        print("working_tree: dirty")
        for line in changes:
            print(f"  {line}")
    else:
        print("working_tree: clean")

    try:
        auth = gh_auth_status()
    except CommandError as exc:
        print(f"gh_auth: unavailable ({exc})")
        return

    print("gh_auth: ok" if auth.returncode == 0 else "gh_auth: missing")


def commit_paths(root: Path, paths: list[str], message: str) -> None:
    if not paths:
        raise CommandError("Commit requires at least one explicit path.")

    resolved_paths = []
    for value in paths:
        path = (root / value).resolve()
        if root not in path.parents and path != root:
            raise CommandError(f"Refusing to stage path outside repo: {value}")
        resolved_paths.append(os.path.relpath(path, root))

    run(["git", "add", "--", *resolved_paths], cwd=root, capture=False)

    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root).stdout.splitlines()
    if not staged:
        raise CommandError("No staged changes to commit.")

    run(["git", "commit", "-m", message], cwd=root, capture=False)


def push_current_branch(root: Path, *, dry_run: bool) -> None:
    ensure_auth(login=False, setup_git=True)

    if origin_url(root) is None:
        raise CommandError("Remote `origin` is missing; add it before pushing.")

    branch = current_branch(root)
    upstream = upstream_ref(root)

    args = ["git", "push"]
    if dry_run:
        args.append("--dry-run")
    if upstream is None:
        args.extend(["-u", "origin", branch])

    run(args, cwd=root, capture=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe gh/git helpers for publishing CP solutions."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the target git repository. Defaults to current directory.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show git remote, branch, changes, and gh auth.")

    auth_parser = subparsers.add_parser("auth", help="Check or initialize gh auth.")
    auth_parser.add_argument(
        "--login",
        action="store_true",
        help="Run `gh auth login --web` when not authenticated.",
    )
    auth_parser.add_argument(
        "--no-setup-git",
        action="store_true",
        help="Skip `gh auth setup-git` after authentication succeeds.",
    )

    commit_parser = subparsers.add_parser(
        "commit", help="Commit only the explicit paths provided."
    )
    commit_parser.add_argument("-m", "--message", required=True, help="Commit message.")
    commit_parser.add_argument("paths", nargs="+", help="Paths to stage and commit.")

    push_parser = subparsers.add_parser("push", help="Push current branch to origin.")
    push_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be pushed."
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        root = repo_root(Path(args.repo).resolve())

        if args.command == "status":
            print_status(root)
        elif args.command == "auth":
            ensure_auth(login=args.login, setup_git=not args.no_setup_git)
        elif args.command == "commit":
            commit_paths(root, args.paths, args.message)
        elif args.command == "push":
            push_current_branch(root, dry_run=args.dry_run)
        else:
            parser.error(f"Unknown command: {args.command}")
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, end="", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        return exc.returncode
    except CommandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
