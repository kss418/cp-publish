---
name: cp-publish
description: Publish local competitive programming solutions to GitHub. Use when Codex needs to organize, validate, commit, or push AtCoder or Codeforces solutions, especially when it must check dependencies, verify GitHub CLI authentication, preserve unrelated changes, and safely use git/gh.
---

# CP Publish

Use this skill to publish local AtCoder or Codeforces solutions into configured Git repositories. The normal path is:

1. Check dependencies and GitHub auth.
2. Validate repository routing config.
3. Build a publish plan.
4. Apply the plan with the bundled plan applier.
5. Validate, commit explicit paths, and push safely.

For exact command examples, load `references/workflow.md`. For placement and README details, load only the reference file needed for the current step:

- `references/path-rules.md`: target path and supported language extension rules.
- `references/readme-format.md`: contest README structure and rating/result table rules.
- `references/solution-tags.md`: tag inference rules.
- `references/solvedac-tag-map.json`: allowed README tag values and solved.ac key mapping.

## Hard Rules

- Do not solve or submit the competitive programming problem unless explicitly asked.
- Do not publish when the contest/problem identity is ambiguous.
- Do not infer the target repository from filenames, URLs, or the current directory; use configured routes only.
- Do not place a solution outside the resolved route target base.
- Do not overwrite an existing solution unless the user clearly intended that update.
- Do not run destructive git commands, force-push, rewrite history, or commit unrelated changes.
- Do not ask for or store GitHub tokens, passwords, cookies, or credentials.
- Do not pass passwords through `sudo -S` or leave a command waiting at a sudo password prompt.
- If validation fails, do not push unless the user explicitly asks to publish anyway.

## Dependency And Auth Gate

Before identifying, moving, committing, or pushing any solution, run:

```powershell
python scripts/check_dependencies.py
```

```sh
python3 scripts/check_dependencies.py
```

Required tools are `git`, `gh`, and `python`. If a dependency is missing, stop before modifying files. Use `scripts/install_dependencies.py --dry-run` to preview installation and ask the user before running an installer. In Codex-run workflows, use `--yes` only after explicit approval.

If a dry-run install plan says `automatic: no` or contains `sudo`/`pkexec`, do not run it from Codex. Show the command and ask the user to run the OS administration step in their own terminal. On Linux, missing `gh` should install without sudo through `scripts/install_gh_user.py`.

Verify GitHub CLI auth before publishing:

```powershell
python scripts/github_integration.py auth
```

```sh
python3 scripts/github_integration.py auth
```

Run `auth --login` only after user approval. In Codex-run workflows, request network escalation for auth checks and login from the first attempt. Tell the user that GitHub may show a one-time code in the command output.

## Repository Routing

Before planning, validate repository routing config:

```powershell
python scripts/configure_repos.py validate
```

```sh
python3 scripts/configure_repos.py validate
```

Supported platforms are `atcoder` and `codeforces`. A user may configure one or both. After detecting the platform, resolve only that platform route. If config is missing, invalid, or the detected platform has no route, stop and ask the user to configure it.

If the resolved route has no `user_id`, ask for the user's AtCoder ID or Codeforces handle and save it with:

```text
scripts/configure_repos.py user <platform> --id <id>
```

Load `references/workflow.md` for full init/resolve examples.

## Planning

Always build a JSON plan before moving files, updating README files, committing, or pushing:

```powershell
python scripts/plan_publish.py C:\path\to\solution.cpp --tags DP,Greedy
```

```sh
python3 scripts/plan_publish.py /path/to/solution.cpp --tags DP,Greedy
```

The plan combines detection, configured routing, path rules, README updates, and metadata. Inspect at least:

- `source`
- `platform`
- `targets`
- `readme_updates`
- `commit_message`
- `needs_confirmation`
- `warnings`
- `detection.conflicts`

If `needs_confirmation` is `true`, stop and ask the user to confirm the risky or ambiguous details before applying the plan. Only rerun `apply_plan.py` with `--allow-confirmation` after that explicit confirmation.

## Confirmation Triggers

Ask before modifying files when any of these are true:

- The source filename is weak, such as `a.cpp`, `main.py`, `solution.cpp`, or `solve.rs`.
- Multiple candidate solution files are plausible.
- The platform, contest ID, problem ID, Codeforces round number, contest kind, contest group, or problem title cannot be determined confidently.
- Detection sources conflict, for example source URL and filename identify different problems.
- README tags are missing or uncertain.
- The source extension is unknown.
- A target path already exists.
- Metadata or result fetches fail and local evidence is insufficient.
- A Codeforces combined Div. 1 + Div. 2 paired target is plausible but unclear.

When asking, show the source path, platform, contest ID, Codeforces round/group/kind when relevant, problem ID, problem title, target path or targets, and the specific warning/conflict.

## Applying Plans

Use `scripts/apply_plan.py` instead of hand-composing copy/move and README commands.

```powershell
python scripts/plan_publish.py C:\path\to\solution.cpp --tags DP,Greedy > C:\path\to\cp-plan.json
python scripts/apply_plan.py --plan C:\path\to\cp-plan.json --copy --dry-run
python scripts/apply_plan.py --plan C:\path\to\cp-plan.json --copy
```

```sh
python3 scripts/plan_publish.py /path/to/solution.cpp --tags DP,Greedy > /tmp/cp-plan.json
python3 scripts/apply_plan.py --plan /tmp/cp-plan.json --copy --dry-run
python3 scripts/apply_plan.py --plan /tmp/cp-plan.json --copy
```

`apply_plan.py` verifies the source file, creates target parents, copies or moves the solution, calls `scripts/update_readme.py`, and prints `changed_paths` plus `commit_paths`. For multiple Codeforces targets, copy the same source to every target; do not move to only one target.

## Metadata And README Rules

Load `references/path-rules.md` when checking placement or target paths. Load `references/readme-format.md` and `references/solution-tags.md` before README-specific edits or tag inference.

Use Codeforces metadata for Codeforces contest names, contest kinds, problem names, and ratings. Use AtCoder/Kenkoooo metadata for AtCoder problem titles and estimated difficulty. Use `--refresh` only when the user explicitly requests fresh metadata.

If network metadata or result fetches fail because sandbox access is blocked, request approval to rerun the same command with network access. If the user does not approve or the API remains unavailable, continue only when local evidence is sufficient; otherwise ask for confirmation.

Use only README tags that appear as values in `references/solvedac-tag-map.json`; solved.ac keys may be converted through that map. Do not invent fallback tag names.

## Publish Workflow

1. Inspect the relevant working tree and preserve unrelated changes.
2. Run dependency and auth gates.
3. Validate repository routing.
4. Identify the candidate solution file.
5. Build and inspect a plan.
6. Resolve any `needs_confirmation`, warnings, or conflicts with the user.
7. Run `apply_plan.py --copy --dry-run`, inspect the JSON, then run without `--dry-run`.
8. Use returned `commit_paths` as the explicit commit target list.
9. Run lightweight validation for the solution language when practical.
10. Commit with the planned commit message or a concise equivalent.
11. Push with `git`/`gh` without force-pushing.

## GitHub Commit And Push

Use the bundled GitHub helper where possible:

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

Commit message examples:

- `Add AtCoder ABC350 A solution`
- `Add Codeforces 1094A solution`
- `Update AtCoder ABC350 B solution`
