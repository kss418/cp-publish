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

## Codeforces Metadata

Run `scripts/codeforces_metadata.py` whenever Codeforces contest names, contest kinds, problem names, or problem ratings are needed for path placement or README updates. The script automatically uses a fresh-enough cache and fetches from the Codeforces API when the cache is missing or stale.

```powershell
python scripts/codeforces_metadata.py contests
python scripts/codeforces_metadata.py problems
python scripts/codeforces_metadata.py all
```

```sh
python3 scripts/codeforces_metadata.py contests
python3 scripts/codeforces_metadata.py problems
python3 scripts/codeforces_metadata.py all
```

Use `--refresh` only when the user explicitly requests fresh metadata.

If a metadata fetch fails because network access is blocked by the sandbox, request approval to rerun the same metadata command with network access. If the user does not approve or the API remains unavailable, continue only when the available local evidence is sufficient; otherwise ask the user to confirm the missing contest/problem metadata.

## AtCoder Metadata

Run `scripts/atcoder_metadata.py` whenever AtCoder contest lists, problem titles, contest-problem mappings, or estimated problem ratings are needed for path placement or README updates. The script automatically uses a fresh-enough cache and fetches from Kenkoooo AtCoder Problems when the cache is missing or stale.

```powershell
python scripts/atcoder_metadata.py contests
python scripts/atcoder_metadata.py problems
python scripts/atcoder_metadata.py merged-problems
python scripts/atcoder_metadata.py contest-problems
python scripts/atcoder_metadata.py ratings
python scripts/atcoder_metadata.py all
python scripts/atcoder_metadata.py problem abc422_a
python scripts/atcoder_metadata.py rating abc422_a
```

```sh
python3 scripts/atcoder_metadata.py contests
python3 scripts/atcoder_metadata.py problems
python3 scripts/atcoder_metadata.py merged-problems
python3 scripts/atcoder_metadata.py contest-problems
python3 scripts/atcoder_metadata.py ratings
python3 scripts/atcoder_metadata.py all
python3 scripts/atcoder_metadata.py problem abc422_a
python3 scripts/atcoder_metadata.py rating abc422_a
```

Use Kenkoooo estimated difficulty as the AtCoder README rating when available. If the estimated difficulty is missing or unknown, write `$-$` for the rating. Use `--refresh` only when the user explicitly requests fresh metadata.

If a metadata fetch fails because network access is blocked by the sandbox, request approval to rerun the same metadata command with network access. If the user does not approve or the API remains unavailable, continue only when the available local evidence is sufficient; otherwise ask the user to confirm the missing contest/problem metadata.

## File Placement Rules

Before moving or copying a solution, load `references/path-rules.md`.

Use the configured route from `configure_repos.py resolve <platform>` as the root destination. Every final path must be inside the resolved `target_base`.

Apply `references/path-rules.md` to determine the path or paths below `target_base`. If the rule cannot determine the target path set, or if any target path already exists, ask the user before modifying files.

For Codeforces combined Div. 1 + Div. 2 problems, `references/path-rules.md` may require multiple target paths. Copy the same solution to each target path and commit all of them together.

## Contest README Updates

Before creating or updating AtCoder or Codeforces contest `README.md` files, load:

- `references/readme-format.md`
- `references/solution-tags.md`

Use Codeforces metadata for Codeforces problem ratings when available. Use Kenkoooo estimated difficulty for AtCoder ratings when available. If rating metadata is missing, follow `references/readme-format.md` and write `$-$`. Infer README tags from the solution code using `references/solution-tags.md`.

Only load `references/solvedac-tag-map.json` when converting a solved.ac tag key or when the common tags in `references/solution-tags.md` do not cover the technique. If tag inference is uncertain, ask the user before updating the README.

Use `scripts/update_readme.py` to create or update a contest README entry:

```powershell
python scripts/update_readme.py --contest-dir C:\path\to\contest --contest-url https://codeforces.com/contest/2061 --problem-id A --rating 800 --tags Case_Work
python scripts/update_readme.py --contest-dir C:\path\to\contest --contest-url https://atcoder.jp/contests/abc422 --problem-id A --rating - --tags Case_Work
```

```sh
python3 scripts/update_readme.py --contest-dir /path/to/contest --contest-url https://codeforces.com/contest/2061 --problem-id A --rating 800 --tags Case_Work
python3 scripts/update_readme.py --contest-dir /path/to/contest --contest-url https://atcoder.jp/contests/abc422 --problem-id A --rating - --tags Case_Work
```

## Publish Plan

Before moving files, updating README files, committing, or pushing, build a dry-run publish plan with `scripts/plan_publish.py` whenever a candidate source file is known.

```powershell
python scripts/plan_publish.py C:\path\to\solution.cpp --tags DP,Greedy
```

```sh
python3 scripts/plan_publish.py /path/to/solution.cpp --tags DP,Greedy
```

The script combines solution detection, configured repository routing, path rules, and platform metadata. It prints JSON shaped like:

```json
{
  "source": "...",
  "targets": ["..."],
  "readme_updates": [
    {
      "readme": "...",
      "contest_url": "...",
      "problem_id": "...",
      "rating": "$-$",
      "tags": "..."
    }
  ],
  "commit_message": "...",
  "needs_confirmation": false
}
```

If `needs_confirmation` is `true`, stop and ask the user to confirm the ambiguous or risky parts before modifying files. Common confirmation triggers include weak detection evidence, missing README tags, missing AtCoder problem title, unknown Codeforces contest kind, unknown source extension, or an existing target file.

When network metadata is unavailable because sandbox access is blocked, request approval to rerun the same planning command with network access. If metadata is still unavailable, continue only when the user confirms the missing contest/problem details.

## Publish Workflow

1. Inspect the working tree of the configured target repositories.
2. Validate repository routing config.
3. Identify the candidate solution file from the user prompt, recent changes, or current directory.
4. Detect platform, contest ID, problem ID, and language.
5. Prefer detection signals in this order:
   - Explicit problem URL in source comments.
   - Structured metadata comments.
   - Existing directory path.
   - Filename pattern.
   - User prompt.
6. If confidence is low or multiple problems are plausible, ask the user for confirmation before modifying files.
7. Resolve the configured route for the detected platform.
8. Run `scripts/plan_publish.py` for the candidate source and inspect the JSON plan.
9. If `needs_confirmation` is `true`, ask the user to confirm before modifying files.
10. Load `references/path-rules.md` and use the planned target path or paths under the resolved `target_base`.
11. Move or copy the solution into the resolved repository and base directory. For multiple Codeforces targets, copy to every target.
12. Load `references/readme-format.md` and `references/solution-tags.md`, then update the contest `README.md`. Update other README, index, or problem list files when the repository uses them.
13. Run lightweight validation for the solution language when practical.
14. Commit only the relevant solution and index changes.
15. Push with `git`/`gh` without force-pushing.

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
