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

## Publish Workflow

1. Inspect the git repository and working tree.
2. Identify the candidate solution file from the user prompt, recent changes, or current directory.
3. Detect platform, contest ID, problem ID, language, and target path.
4. Prefer detection signals in this order:
   - Explicit problem URL in source comments.
   - Structured metadata comments.
   - Existing directory path.
   - Filename pattern.
   - User prompt.
5. If confidence is low or multiple problems are plausible, ask the user for confirmation before modifying files.
6. Move or copy the solution into the repository convention.
7. Update README, index, or problem list files when the repository uses them.
8. Run lightweight validation for the solution language when practical.
9. Commit only the relevant solution and index changes.
10. Push with `git`/`gh` without force-pushing.

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
