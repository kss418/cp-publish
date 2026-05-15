#!/usr/bin/env python3
"""Safe GitHub CLI helpers for competitive-programming publish workflows."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from check_dependencies import install_command, tool_path

GITHUB_DEVICE_URL = "https://github.com/login/device"


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
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def require_tool(name: str) -> str:
    path = tool_path(name)
    if path is None:
        hint = install_command(name)
        message = f"Required dependency not found on PATH: {name}"
        if hint:
            message = f"{message}\ninstall_command: {hint}"
        raise CommandError(message)
    return path


def repo_root(start: Path) -> Path:
    result = run([require_tool("git"), "rev-parse", "--show-toplevel"], cwd=start)
    return Path(result.stdout.strip()).resolve()


def current_branch(root: Path) -> str:
    result = run([require_tool("git"), "branch", "--show-current"], cwd=root)
    branch = result.stdout.strip()
    if not branch:
        raise CommandError("Detached HEAD is not supported for publishing.")
    return branch


def git_porcelain(root: Path) -> list[str]:
    result = run([require_tool("git"), "status", "--porcelain"], cwd=root)
    return [line for line in result.stdout.splitlines() if line.strip()]


def upstream_ref(root: Path) -> str | None:
    result = run(
        [
            require_tool("git"),
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ],
        cwd=root,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def origin_url(root: Path) -> str | None:
    result = run(
        [require_tool("git"), "remote", "get-url", "origin"],
        cwd=root,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def gh_auth_status() -> subprocess.CompletedProcess[str]:
    return run([require_tool("gh"), "auth", "status"], check=False)


def open_browser_url(url: str) -> bool:
    try:
        return webbrowser.open(url, new=2)
    except Exception as exc:
        print(f"Could not open browser automatically: {exc}", file=sys.stderr)
    return False


def print_device_code_hint() -> None:
    print(
        "When GitHub asks for a one-time code, copy it from the terminal output below."
    )
    print(
        "In Codex, open or click the command output/terminal panel if the code is not visible in chat."
    )


def gh_auth_login_web(*, open_browser: bool) -> None:
    gh = require_tool("gh")
    if open_browser:
        print(f"Opening GitHub browser login: {GITHUB_DEVICE_URL}")
        if not open_browser_url(GITHUB_DEVICE_URL):
            print(f"Open this URL manually if no browser appears: {GITHUB_DEVICE_URL}", file=sys.stderr)
    else:
        print("Starting GitHub browser login...")

    print_device_code_hint()

    run(
        [gh, "auth", "login", "--web", "--git-protocol", "https"],
        check=True,
        capture=False,
        input_text="\n",
    )


def ensure_auth(*, login: bool, setup_git: bool, open_browser: bool = True) -> None:
    status = gh_auth_status()
    if status.returncode != 0:
        if not login:
            raise CommandError(
                "GitHub CLI is not authenticated. Run this command again with "
                "`auth --login`, or run `gh auth login --web --git-protocol https` yourself."
            )
        gh_auth_login_web(open_browser=open_browser)

    status = gh_auth_status()
    if status.returncode != 0:
        raise CommandError("GitHub CLI authentication still failed after login.")

    if setup_git:
        run([require_tool("gh"), "auth", "setup-git"], check=True, capture=False)


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

    git = require_tool("git")
    run([git, "add", "--", *resolved_paths], cwd=root, capture=False)

    staged = run([git, "diff", "--cached", "--name-only"], cwd=root).stdout.splitlines()
    if not staged:
        raise CommandError("No staged changes to commit.")

    run([git, "commit", "-m", message], cwd=root, capture=False)


def push_current_branch(root: Path, *, dry_run: bool) -> None:
    ensure_auth(login=False, setup_git=True)

    if origin_url(root) is None:
        raise CommandError("Remote `origin` is missing; add it before pushing.")

    branch = current_branch(root)
    upstream = upstream_ref(root)

    args = [require_tool("git"), "push"]
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
        help="Run browser-based `gh auth login --web --git-protocol https` when not authenticated.",
    )
    auth_parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Do not ask Codex/Python to open the GitHub login page before running gh.",
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
            ensure_auth(
                login=args.login,
                setup_git=not args.no_setup_git,
                open_browser=not args.no_open_browser,
            )
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
