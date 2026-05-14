---
name: cp-publish
description: Publish local competitive programming solutions to GitHub. Use when Codex needs to organize, validate, commit, or push AtCoder or Codeforces solutions, especially when it must check dependencies, verify GitHub CLI authentication, preserve unrelated changes, and safely use git/gh.
---

# CP Publish 

## Dependency Check

Run the dependency check before identifying, moving, committing, or pushing any solution. Use the Python executable available on the current platform:

```powershell
python scripts/check_dependencies.py
```

```sh
python3 scripts/check_dependencies.py
```

Use JSON output when another script or structured decision needs the result:

```powershell
python scripts/check_dependencies.py --json
```

```sh
python3 scripts/check_dependencies.py --json
```

Require these dependencies:

- `git`: inspect, stage, commit, and push repository changes.
- `gh`: check GitHub authentication and configure git credentials.
- `python`: run the helper scripts in this skill.

If any required dependency is missing, stop the publish workflow before modifying files, committing, or pushing. Read `install_command` or `install_commands` from `scripts/check_dependencies.py`, tell the user which dependency is missing, and ask for approval to install it with the platform-specific command or command sequence.

The dependency checker chooses install commands for the current OS and available package manager:

- Windows: `winget`, `choco`, or `scoop`.
- macOS: `brew`, MacPorts, or `conda`.
- Linux: Homebrew, `apt`, `dnf`, `yum`, `zypper`, `pacman`, `apk`, or `conda`.

Ask with the exact command or command sequence:

```text
GitHub CLI (`gh`) is required for publishing. May I install it with the command(s) below?
<install command(s) from scripts/check_dependencies.py>
```

Only after the user approves, run the command or command sequence in the native shell. After installation, rerun the dependency check with the same Python executable:

```powershell
python scripts/check_dependencies.py
```

```sh
python3 scripts/check_dependencies.py
```

If the install fails, report the failure and do not continue publishing.

After `gh` is installed, verify authentication before publishing:

```powershell
python scripts/github_integration.py auth
```

```sh
python3 scripts/github_integration.py auth
```

If authentication is missing and the user approves an interactive login, use:

```powershell
python scripts/github_integration.py auth --login
```

```sh
python3 scripts/github_integration.py auth --login
```

Never ask for or store GitHub tokens, passwords, cookies, or credentials in project files, logs, commits, or skill resources.

## Repository Routing

After GitHub authentication and before identifying the solution file, require repository routing config. Do not infer the target repository from filenames, URLs, or the current directory.

The only supported platforms are:

- `atcoder`
- `codeforces`

Config may contain one or both platform routes. A Codeforces-only user must not be blocked by a missing AtCoder route, and an AtCoder-only user must not be blocked by a missing Codeforces route.

Create or update config interactively with:

```powershell
python scripts/configure_repos.py init
```

```sh
python3 scripts/configure_repos.py init
```

Configure only one platform with:

```powershell
python scripts/configure_repos.py init --platform codeforces --codeforces-repo C:\path\to\codeforces --codeforces-base-dir .
python scripts/configure_repos.py init --platform atcoder --atcoder-repo C:\path\to\atcoder --atcoder-base-dir .
```

```sh
python3 scripts/configure_repos.py init --platform codeforces --codeforces-repo /path/to/codeforces --codeforces-base-dir .
python3 scripts/configure_repos.py init --platform atcoder --atcoder-repo /path/to/atcoder --atcoder-base-dir .
```

For split repositories:

```powershell
python scripts/configure_repos.py init --platform both --atcoder-repo C:\path\to\atcoder --codeforces-repo C:\path\to\codeforces --atcoder-base-dir . --codeforces-base-dir .
```

```sh
python3 scripts/configure_repos.py init --platform both --atcoder-repo /path/to/atcoder --codeforces-repo /path/to/codeforces --atcoder-base-dir . --codeforces-base-dir .
```

For one repository with platform folders:

```powershell
python scripts/configure_repos.py init --platform both --atcoder-repo C:\path\to\cp-solutions --codeforces-repo C:\path\to\cp-solutions --atcoder-base-dir atcoder --codeforces-base-dir codeforces
```

```sh
python3 scripts/configure_repos.py init --platform both --atcoder-repo /path/to/cp-solutions --codeforces-repo /path/to/cp-solutions --atcoder-base-dir atcoder --codeforces-base-dir codeforces
```

Validate config before publishing:

```powershell
python scripts/configure_repos.py validate
```

```sh
python3 scripts/configure_repos.py validate
```

If config is missing or invalid, stop and ask the user to configure at least one repository route. Do not scan, move, commit, or push solutions until config validates.

After detecting the platform, resolve only that platform route:

```powershell
python scripts/configure_repos.py resolve atcoder
python scripts/configure_repos.py resolve codeforces
```

```sh
python3 scripts/configure_repos.py resolve atcoder
python3 scripts/configure_repos.py resolve codeforces
```

Use the resolved `repo_path` and `base_dir` as the only target destination for the solution.

If the detected platform has no configured route, stop and ask the user to add that platform route. Do not fall back to another platform's repository.

## Publish Workflow

1. Inspect the working tree of the configured target repositories.
2. Validate repository routing config.
3. Identify the candidate solution file from the user prompt, recent changes, or current directory.
4. Detect platform, contest ID, problem ID, language, and route-based target path.
5. Prefer detection signals in this order:
   - Explicit problem URL in source comments.
   - Structured metadata comments.
   - Existing directory path.
   - Filename pattern.
   - User prompt.
6. If confidence is low or multiple problems are plausible, ask the user for confirmation before modifying files.
7. Move or copy the solution into the resolved repository and base directory.
8. Update README, index, or problem list files when the repository uses them.
9. Run lightweight validation for the solution language when practical.
10. Commit only the relevant solution and index changes.
11. Push with `git`/`gh` without force-pushing.

## GitHub Helpers

Use the bundled GitHub helper for safe status, auth, commit, and push operations:

```powershell
python scripts/github_integration.py status
python scripts/github_integration.py commit -m "Add AtCoder ABC350 A solution" path/to/file.cpp
python scripts/github_integration.py push --dry-run
python scripts/github_integration.py push
```

```sh
python3 scripts/github_integration.py status
python3 scripts/github_integration.py commit -m "Add AtCoder ABC350 A solution" path/to/file.cpp
python3 scripts/github_integration.py push --dry-run
python3 scripts/github_integration.py push
```

Stage and commit only explicit paths. Preserve unrelated user changes in the working tree.

## Safety Rules

- Do not solve or submit the competitive programming problem unless explicitly asked.
- Do not publish when the contest/problem identity is ambiguous.
- Do not overwrite an existing solution unless it clearly refers to the same problem and the user intended an update.
- Do not run destructive git commands.
- Do not force-push or rewrite git history.
- Do not commit unrelated changes.
- If validation fails, do not push unless the user explicitly asks to publish anyway.

## Commit Message Style

Use concise commit messages:

- `Add AtCoder ABC350 A solution`
- `Add Codeforces 1900A solution`
- `Update AtCoder ABC350 B solution`
