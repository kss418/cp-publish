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
- `references/codeforces-contest-rule-map.json`: Codeforces contest kind, exact title override, Others group, and round-number rule mapping.

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

## Workspace And Sandbox Guard

Treat the skill directory as read-only runtime code. Before running commands that create plan files, move/copy solutions, update README files, write `.git/index`, or push, set the command working directory to the resolved target repository or another known writable workspace, not to the skill installation directory. Invoke bundled scripts by absolute path when the working directory is not the skill root.

Keep temporary plan JSON files inside the resolved target repository, the resolved `target_base`, or an OS temp directory known to be writable. Create the parent directory from that writable working directory before writing, remove temporary plan files before committing, and never place plan files in the skill directory or an arbitrary current directory.

If a command needs to write outside the active writable root, update `.git/index`, use the GitHub CLI keyring, or access the network for metadata/results/auth/push, request escalation on the first attempt. If a write fails with `Access is denied`, `Permission denied`, `index.lock`, or Git `safe.directory`/ownership errors, stop retrying from the skill directory and rerun from the target repository with the required escalation.

## Session Gate Cache

Within one Codex session, cache successful dependency, GitHub auth, and repository route checks by platform and repository path. For repeated publishes to the same resolved repository in the same session, reuse those checks instead of rerunning them.

Invalidate the session cache and rerun the relevant gate when the target repository path, platform, route config, `user_id`, GitHub account, remote, branch, Python environment, or tool availability changes, or when a git/gh/network command fails in a way that could be auth or config related. Never reuse a cached failure.

This cache only skips gates. Still inspect the current working tree before each publish, still build/apply plans for each publish, and still commit only explicit paths.

Planning shares parsed platform metadata in memory for one single/batch invocation, including title detection and target planning. A later invocation gets a new snapshot; `--refresh-metadata` refreshes each resource once per invocation. This does not cache auth or routing decisions.

## Efficient Tool Calls

After dependency and route checks pass, run independent source/reference reads and local repository inspections in parallel, awaiting and inspecting every result. Group related verification commands in one shell call and check each exit code before continuing. Keep approval requests and mutations sequential; wait for running sessions to finish before dependent work. See "Grouped Checks" in `references/workflow.md` for execution groups and examples.

## Solution Build Validation

Do not compile, run, submit, or otherwise execute competitive programming solution code as part of the default publish workflow. Treat publishing as metadata, placement, README, git, and push work only.

Compile or run a solution only when the user explicitly asks for it, when the task is to debug/verify the solution itself, or when local evidence suggests the file is corrupted or not the language/extension it claims to be. If compilation is requested, keep it separate from publish gating and report it as an optional verification result.

## Dependency And Auth Gate

Before identifying, moving, committing, or pushing any solution, run:

```powershell
python scripts/init/check_dependencies.py
```

```sh
python3 scripts/init/check_dependencies.py
```

Required tools are `git`, `gh`, and `python`. If a dependency is missing, stop before modifying files. Use `scripts/init/install_dependencies.py --dry-run` to preview installation and ask the user before running an installer. In Codex-run workflows, use `--yes` only after explicit approval.

If a dry-run install plan says `automatic: no` or contains `sudo`/`pkexec`, do not run it from Codex. Show the command and ask the user to run the OS administration step in their own terminal. On Linux, missing `gh` should install without sudo through `scripts/init/install_gh_user.py`.

Verify GitHub CLI auth before publishing:

```powershell
python scripts/init/github_integration.py auth
```

```sh
python3 scripts/init/github_integration.py auth
```

Run `auth --login` only after user approval. In Codex-run workflows, request network escalation for auth checks and login from the first attempt. Tell the user that GitHub may show a one-time code in the command output.

## Repository Routing

Before applying a plan, resolve the detected platform route. Use platform-scoped validation and do not fail a publish only because an unused platform route is broken:

```powershell
python scripts/init/configure_repos.py validate --platform <platform>
python scripts/init/configure_repos.py resolve <platform>
```

```sh
python3 scripts/init/configure_repos.py validate --platform <platform>
python3 scripts/init/configure_repos.py resolve <platform>
```

Supported platforms are `atcoder` and `codeforces`. A user may configure one or both. After detecting the platform, resolve only that platform route. If config is missing, invalid, or the detected platform has no route, stop and ask the user to configure it.

If the resolved route has no `user_id`, ask for the user's AtCoder ID or Codeforces handle and save it with:

```text
scripts/init/configure_repos.py user <platform> --id <id>
```

Load `references/workflow.md` for full init/resolve examples.

## Planning

Always build a JSON plan before moving files, updating README files, committing, or pushing:

```powershell
$skillRoot = "C:\path\to\cp-publish-skill"
Set-Location C:\path\to\resolved\repo
python "$skillRoot\scripts\cp_publish\plan_publish.py" C:\path\to\solution.cpp --tags DP,Greedy
```

```sh
skill_root=/path/to/cp-publish-skill
cd /path/to/resolved/repo
python3 "$skill_root/scripts/cp_publish/plan_publish.py" /path/to/solution.cpp --tags DP,Greedy
```

The plan combines detection, configured routing, path rules, README updates, and metadata. Inspect at least:

- `source`
- `source_sha256`
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
- A Java source declares a public class that does not match the planned renamed target filename.
- A target path already exists.
- Metadata or result fetches fail and local evidence is insufficient.
- A Codeforces combined Div. 1 + Div. 2 paired target is plausible but unclear.

When asking, show the source path, platform, contest ID, Codeforces round/group/kind when relevant, problem ID, problem title, target path or targets, and the specific warning/conflict.

## Applying Plans

Use `scripts/cp_publish/apply_plan.py` instead of hand-composing copy/move and README commands.

For multiple solution files, prefer `scripts/cp_publish/batch_publish.py` over repeated single-file `plan_publish.py` and `apply_plan.py` calls. It builds one plan per source, prints one batch dry-run summary, applies plans in one loop, shares contest result fetches by command so each contest/user result is fetched once, and returns combined `commit_paths` plus a `suggested_commit_message`.

For non-trivial batches, save the dry-run plan with `--save-plan .cp-publish-plans/batch.json`, inspect the JSON, then apply it with `--apply-plan .cp-publish-plans/batch.json`. This reuses the plans from dry-run and skips rebuilding detection/metadata during apply.

Successful dry-run result payloads are embedded in the saved plan and reused for up to 300 seconds only for the exact same result command (including contest and user). Expired, invalid, or unmatched records invoke the normal result helper. Use `--no-saved-results` to bypass embedded results; the helper's normal API cache still applies. Failures are never embedded, and reuse does not renew the original timestamp. `result_fetches[].from_saved_plan` reports this reuse.

Plans include the source SHA-256. Apply rejects changed sources and older plans without a fingerprint; regenerate and inspect the plan instead of bypassing this check. Sources are rechecked after README preparation and before file operations.

README updates are validated and rendered together per destination in-process, then written once per changed README. README and saved-plan text writes use a same-directory temporary file followed by replacement, so a failed write preserves the existing destination. This is per-file protection, not rollback of a whole multi-file publish. Repeated result commands share successes and failures within an apply invocation; only successful results can also be embedded in saved plans as described above. A failed lookup is tried again on a later invocation. Gate-cache rules remain unchanged.

Use `--from-dir <dir>` for a contest folder, or pass multiple file paths directly. Use `--problem-id-from-filename` only when the filename prefix is trusted as the problem id. For AtCoder, a supplied `--contest-id` also enables exact normalized-title matching within that contest, so a source such as `Too_Many_Requests.cpp` can resolve to its problem label without renaming.

When batch sources need different problem IDs, titles, ratings, or tags, use `--manifest <json>` instead of repeating single-file plans. The manifest is keyed by source path and each value may contain `problem_id`, `problem_title`, `rating`, and `tags`.

```powershell
$skillRoot = "C:\path\to\cp-publish-skill"
$repo = "C:\path\to\resolved\repo"
$planDir = Join-Path $repo ".cp-publish-plans"
New-Item -ItemType Directory -Force -Path $planDir | Out-Null
python "$skillRoot\scripts\cp_publish\plan_publish.py" C:\path\to\solution.cpp --tags DP,Greedy > "$planDir\cp-plan.json"
python "$skillRoot\scripts\cp_publish\apply_plan.py" --plan "$planDir\cp-plan.json" --copy --dry-run
python "$skillRoot\scripts\cp_publish\apply_plan.py" --plan "$planDir\cp-plan.json" --copy
Remove-Item -LiteralPath "$planDir\cp-plan.json"
```

```sh
skill_root=/path/to/cp-publish-skill
repo=/path/to/resolved/repo
plan_dir="$repo/.cp-publish-plans"
mkdir -p "$plan_dir"
python3 "$skill_root/scripts/cp_publish/plan_publish.py" /path/to/solution.cpp --tags DP,Greedy > "$plan_dir/cp-plan.json"
python3 "$skill_root/scripts/cp_publish/apply_plan.py" --plan "$plan_dir/cp-plan.json" --copy --dry-run
python3 "$skill_root/scripts/cp_publish/apply_plan.py" --plan "$plan_dir/cp-plan.json" --copy
rm "$plan_dir/cp-plan.json"
```

`apply_plan.py` verifies the source file, creates target parents, copies or moves the solution, fetches contest results from the plan by default, calls `scripts/cp_publish/update_readme.py`, and prints `changed_paths` plus `commit_paths`. Use `--no-results` only when result lookup should be skipped. Use `--require-results` only when a result fetch failure should fail the apply. For multiple Codeforces targets, copy the same source to every target; do not move to only one target.

Batch example:

```powershell
$planDir = Join-Path $repo ".cp-publish-plans"
New-Item -ItemType Directory -Force -Path $planDir | Out-Null
$batchPlan = Join-Path $planDir "batch.json"
python "$skillRoot\scripts\cp_publish\batch_publish.py" --from-dir C:\path\to\contest --move --dry-run --save-plan "$batchPlan"
python "$skillRoot\scripts\cp_publish\batch_publish.py" --apply-plan "$batchPlan"
Remove-Item -LiteralPath "$batchPlan"
```

```sh
plan_dir="$repo/.cp-publish-plans"
mkdir -p "$plan_dir"
batch_plan="$plan_dir/batch.json"
python3 "$skill_root/scripts/cp_publish/batch_publish.py" --from-dir /path/to/contest --move --dry-run --save-plan "$batch_plan"
python3 "$skill_root/scripts/cp_publish/batch_publish.py" --apply-plan "$batch_plan"
rm "$batch_plan"
```

## Metadata And README Rules

Load `references/path-rules.md` when checking placement or target paths. Load `references/readme-format.md` and `references/solution-tags.md` before README-specific edits or tag inference.

Use Codeforces metadata for Codeforces contest names, contest kinds, problem names, and ratings. Default Codeforces `contest.list` and `problemset.problems` calls should use the bundled `references/codeforces-cache/` snapshots before attempting fresh Codeforces API fetches. Use bundled AtCoder metadata for AtCoder problem titles and estimated difficulty; strip a matching task-label prefix such as `A.` before building the filename, and convert sub-400 raw difficulty to the displayed AtCoder Problems value before writing README ratings. If title resources are unavailable, rely on the bundled official AtCoder tasks-page fallback, which is cached per contest. For `plan_publish.py`, use `--refresh-metadata` only when the user explicitly requests fresh metadata. For metadata and result helper scripts, use `--refresh`.

For Codeforces contest path classification, follow `references/codeforces-contest-rule-map.json` as the canonical editable map. Prefer updating that map for named rounds, special contests, exact one-off title overrides, and Others group aliases instead of adding hard-coded contest-title branches.

For Codeforces result updates, prefer the default `scripts/api/codeforces_results.py contest` path. It fetches the user's bulk `user.status` once, caches that response for 1 hour, and computes per-contest wrong attempts and AC times locally. Do not use `--standings` or `--fallback-standings` unless official standings data is specifically needed or the bulk status path is insufficient.

For AtCoder result updates, use the default `scripts/api/atcoder_results.py contest` path. It checks `scripts/api/atcoder_user_history.py` data from `users/<id>/history/json` first, caches that participation history per user for 1 day by default, and skips standings when the user did not participate in that contest. Use `--no-history-filter` only when the history precheck should be bypassed.

For AtCoder result-table backfills, prefer the bundled cache `references/atcoder-cache/contest_result_table_submissions.zip` when standings is unavailable or many contests need local computation. The zip contains `contest_result_table_submissions.csv`, filtered to official contest-window submissions and reduced to the columns needed for README result tables: `id`, `epoch_second`, `contest_id`, `problem_id`, `user_id`, and `result`. It excludes `CE`, `IE`, and `WJ` rows because they do not affect wrong-attempt counts or AC time. Do not download or regenerate the full AtCoder Problems submissions CSV unless the user explicitly asks.

If network metadata or result fetches fail because sandbox access is blocked, request approval to rerun the same command with network access. If the user does not approve or the API remains unavailable, continue only when local evidence is sufficient; otherwise ask for confirmation.

Use only README tags that appear as values in `references/solvedac-tag-map.json`; solved.ac keys may be converted through that map. Do not invent fallback tag names.

## Publish Workflow

1. Inspect the relevant working tree and preserve unrelated changes.
2. Run dependency and auth gates, or reuse the current-session gate cache when valid.
3. Validate repository routing, or reuse the current-session route cache when valid.
4. Identify the candidate solution file.
5. Build and inspect a plan.
6. Resolve any `needs_confirmation`, warnings, or conflicts with the user.
7. For one file, run `apply_plan.py --copy --dry-run`, inspect the JSON, then run without `--dry-run`; for multiple files, run `batch_publish.py --dry-run --save-plan ...`, inspect the JSON, then apply with `batch_publish.py --apply-plan ...`.
8. Use returned `commit_paths` as the explicit commit target list.
9. Do not compile or run solution code unless the user explicitly asked for solution verification.
10. Commit with the planned commit message or a concise equivalent.
11. Push with `git`/`gh` without force-pushing.

## GitHub Commit And Push

For a push-only follow-up of already prepared changes, let the push helper perform authentication; do not run a separate `gh auth status`, `auth`, or auth-bearing `status` immediately beforehand. Use local git commands for scope inspection. This exception does not remove the early auth gate for a new solution publish.

For latency diagnosis, pass `--timings` before the GitHub helper subcommand. It emits per-process durations to stderr without command arguments or output. Measure before adding caches or weakening checks; do not perform a real push solely to benchmark it.

Use the bundled GitHub helper where possible:

After the commit has been reviewed and pushing is authorized, prefer `push --verify-first`: it checks auth/setup once, runs push dry-run, verifies that HEAD/branch/origin/upstream remain unchanged, then pushes. A failure stops the sequence. This flag performs an actual push; use `push --dry-run` alone when the output still needs human review. No credentials or auth-success files are saved for reuse across processes.

```powershell
$skillRoot = "C:\path\to\cp-publish-skill"
Set-Location C:\path\to\resolved\repo
python "$skillRoot\scripts\init\github_integration.py" status
python "$skillRoot\scripts\init\github_integration.py" commit -m "Add AtCoder ABC350 A solution" path/to/file.cpp
python "$skillRoot\scripts\init\github_integration.py" commit -m "Publish Codeforces solutions" --paths-from-json .cp-publish-plans/batch-result.json
python "$skillRoot\scripts\init\github_integration.py" push --verify-first
```

```sh
skill_root=/path/to/cp-publish-skill
cd /path/to/resolved/repo
python3 "$skill_root/scripts/init/github_integration.py" status
python3 "$skill_root/scripts/init/github_integration.py" commit -m "Add AtCoder ABC350 A solution" path/to/file.cpp
python3 "$skill_root/scripts/init/github_integration.py" commit -m "Publish Codeforces solutions" --paths-from-json .cp-publish-plans/batch-result.json
python3 "$skill_root/scripts/init/github_integration.py" push --verify-first
```

Stage and commit only explicit paths or pathspecs. For large batches, prefer `--paths-from-json <batch-result.json>` when using `batch_publish.py` output, or `--paths-from-file <commit-paths.txt>` for a newline-delimited path list. Directory pathspecs are allowed; the helper expands them through git and still refuses unrelated staged paths.

Commit message examples:

- `Add AtCoder ABC350 A solution`
- `Add Codeforces 1094A solution`
- `Update AtCoder ABC350 B solution`
