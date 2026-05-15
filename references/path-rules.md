# Path Rules

Use these rules after platform detection and after resolving repository routing with:

```text
scripts/init/configure_repos.py resolve <platform>
```

The resolved `target_base` is the root for all file placement. Never place a solution outside `target_base`.

## Supported Platforms

Only these platforms are supported:

- `atcoder`
- `codeforces`

If the platform is not one of these values, stop and ask the user.

## Language Extensions

Preserve the source language by extension. Normalize common extensions as follows:

| Language | Input extensions | Stored extension |
| --- | --- | --- |
| C++ | `.cpp`, `.cc`, `.cxx` | `.cpp` |
| C | `.c` | `.c` |
| Python | `.py`, `.py3` | `.py` |
| Rust | `.rs` | `.rs` |
| Java | `.java` | `.java` |
| JavaScript | `.js` | `.js` |
| Kotlin | `.kt` | `.kt` |
| Kotlin Script | `.kts` | `.kt` |
| Go | `.go` | `.go` |

If the extension is unknown, keep the original extension and ask for confirmation before publishing.

Java remains supported, but it uses the same problem-title filename pattern as other languages, for example `A_Title.java`. Java solutions with `public class Main` may not compile after renaming because a public class name must match the filename. Use non-public `class Main`, or publish Java solutions manually.

## AtCoder

For numeric AtCoder contest series, use:

```text
<target_base>/<series>/<hundreds_bucket>/<tens_bucket>/<contest_number>/<problem_label>_<problem_title_slug>.<ext>
```

For PAST, use:

```text
<target_base>/PAST/<past_contest_key>/<problem_label>_<problem_title_slug>.<ext>
```

Normalize:

- `series`: uppercase contest series. Supported values are `ABC`, `ARC`, `AGC`, `AHC`, and `PAST`.
- `contest_number`: integer contest number without leading zeroes for `ABC`, `ARC`, `AGC`, and `AHC`, for example `422`.
- `hundreds_bucket`: `(contest_number // 100) * 100`, for example `422 -> 400`. Use this for `ABC`, `ARC`, `AGC`, and `AHC`.
- `tens_bucket`: `(contest_number // 10) * 10`, for example `422 -> 420`. Use this for `ABC`, `ARC`, `AGC`, and `AHC`.
- `past_contest_key`: the PAST contest key without the leading `past`, for example `past202309-open -> 202309-open`.
- `problem_label`: problem number or task label, for example `A`, `B`, `C`, or `Ex`.
- `problem_title_slug`: problem title with spaces replaced by underscores and unsafe filename characters removed.
- `ext`: normalized language extension.

Filename format:

```text
<problem_label>_<problem_title_slug>.<ext>
```

Preserve useful capitalization in the problem title, as in `A_Stage_Clear.cpp`. If the problem title is unavailable from reliable metadata, ask the user before publishing.

Examples:

| Signal | Problem title | Target path below `target_base` |
| --- | --- | --- |
| `https://atcoder.jp/contests/abc422/tasks/abc422_a` | `Stage Clear` | `ABC/400/420/422/A_Stage_Clear.cpp` |
| `abc422_a.cpp` | `Stage Clear` | `ABC/400/420/422/A_Stage_Clear.cpp` |
| `ABC422A.py` | `Stage Clear` | `ABC/400/420/422/A_Stage_Clear.py` |
| `arc180_b.cpp` | `Example Title` | `ARC/100/180/180/B_Example_Title.cpp` |
| `agc064_a.rs` | `Example Title` | `AGC/0/60/64/A_Example_Title.rs` |
| `https://atcoder.jp/contests/ahc043/tasks/ahc043_a` | `Example Title` | `AHC/0/40/43/A_Example_Title.cpp` |
| `https://atcoder.jp/contests/past202309-open/tasks/past202309_a` | `Example Title` | `PAST/202309-open/A_Example_Title.cpp` |

Contest series outside `ABC`, `ARC`, `AGC`, `AHC`, and `PAST` are not supported yet. If a source appears to be another AtCoder series, stop and ask the user.

If an AtCoder task suffix contains multiple parts, preserve it as the problem label after normalizing capitalization, for example `abc999_ex -> Ex`.

## Codeforces

For regular numeric Codeforces rounds, use the Codeforces round number:

```text
<target_base>/<hundreds_bucket>/<tens_bucket>/<round_number>/<problem_id>_<problem_title_slug>.<ext>
```

For Educational rounds, use the Educational round number under `Educational`:

```text
<target_base>/Educational/<hundreds_bucket>/<tens_bucket>/<round_number>/<problem_id>_<problem_title_slug>.<ext>
```

For non-regular named contests, use the normalized contest group and the numeric round identifier from the contest name under `Others`:

```text
<target_base>/Others/<contest_group>/<hundreds_bucket>/<tens_bucket>/<round_number>/<problem_id>_<problem_title_slug>.<ext>
```

Normalize:

- `contest_id`: numeric contest ID from the Codeforces URL/API, for example the `2222` in `https://codeforces.com/contest/2222`. Use this for API lookup and README links, not for folder placement.
- `round_number`: numeric identifier parsed from the contest name. This is the folder number. For example, `Spectral::Cup 2026 Round 1 (Codeforces Round 1094, Div. 1 + Div. 2)` uses `1094`, not contest ID `2222`.
- `contest_group`: for `Others` only, a normalized group name derived from the contest title, with spaces and punctuation replaced by underscores.
- `contest_kind`: one of regular numeric contest, Educational contest, or Others. Ignore Div. 1, Div. 2, and Div. 3 labels for path placement.
- `hundreds_bucket`: `(round_number // 100) * 100`, for example `1094 -> 1000`.
- `tens_bucket`: `(round_number // 10) * 10`, for example `1094 -> 1090`.
- `problem_id`: uppercase problem index, preserving multi-part indices such as `A1`, `B2`, or `C`.
- `problem_title_slug`: problem title with spaces replaced by underscores and unsafe filename characters removed.
- `ext`: normalized language extension.

Classify by the Codeforces contest `name` from `contest.list`; do not classify by the API `type` alone. Many official Div. 3, Div. 4, and Educational rounds have API `type` values such as `ICPC`.

Classify as regular numeric contests when the contest name contains an official `Codeforces Round` token, including:

- `Codeforces Round 1098 (Div. 2)`.
- `Codeforces Round 1097 (Div. 1, Based on Zhili Cup 2026)`.
- `Spectral::Cup 2026 Round 1 (Codeforces Round 1094, Div. 1 + Div. 2)`.
- `CodeCraft-22 and Codeforces Round 795 (Div. 2)`.

In other words, company, event, or sponsor text does not make a contest `Others` when the title still contains `Codeforces Round` as an official round token.

Classify as `Educational` when the contest name contains `Educational Codeforces Round`. Extract the number after that token.

Classify these as `Others` and use these preferred group names when applicable:

- Codeforces Global rounds: `Global_Round`. Use the Global Round number.
- Hello rounds: `Hello`. Use the last two digits of the year, for example `Hello 2026 -> 26`.
- Good Bye rounds: `Good_Bye`. Use the last two digits of the year, for example `Good Bye 2022 -> 22`.
- April Fools contests: `April_Fools`. Use the numeric contest/round identifier when present; if the title only gives a year, use the last two digits of that year.
- Kotlin Heroes: `Kotlin_Heroes`. Use the episode/practice number.
- Testing Round: `Testing_Round`. Use the testing round number.
- ICPC, IOI, regional, online mirror, and team-preferred contests: prefer `ICPC` or `IOI` when those tokens are present.
- Company, product, sponsor, or event named contests that do not contain the official `Codeforces Round` token, such as `CodeTON Round`, `Pinely Round`, `Deltix Round`, and `Harbour.Space Scholarship Contest`. Normalize the series name and use the series round number when present.

If no `contest_group` or numeric round identifier can be determined from the contest name, ask the user for `contest_group` and/or `round_number` before publishing. Do not silently fall back to the Codeforces contest ID for folder placement.

Examples:

| Signal | Target path below `target_base` |
| --- | --- |
| `https://codeforces.com/contest/2228/problem/A` with `Codeforces Round 1098 (Div. 2)` and title `Example Title` | `1000/1090/1098/A_Example_Title.cpp` |
| `https://codeforces.com/contest/2222/problem/A` with `Spectral::Cup 2026 Round 1 (Codeforces Round 1094, Div. 1 + Div. 2)` and title `Example Title` | `1000/1090/1094/A_Example_Title.cpp` |
| Educational contest ID `2225`, `Educational Codeforces Round 189`, problem `A`, title `Example Title` | `Educational/100/180/189/A_Example_Title.cpp` |
| `CodeTON Round 9`, contest ID `2039`, problem `B`, title `Example Title` | `Others/CodeTON_Round/0/0/9/B_Example_Title.cpp` |
| `Codeforces Global Round 11`, problem `C`, title `Example Title` | `Others/Global_Round/0/10/11/C_Example_Title.cpp` |
| `Hello 2026`, problem `A`, title `Example Title` | `Others/Hello/0/20/26/A_Example_Title.cpp` |
| `Good Bye 2022`, problem `A`, title `Example Title` | `Others/Good_Bye/0/20/22/A_Example_Title.cpp` |
| `April Fools Contest 3`, problem `A`, title `Example Title` | `Others/April_Fools/0/0/3/A_Example_Title.cpp` |

If the contest looks Educational but the round number is unclear, ask the user before publishing.

If the contest looks like Global, Hello, Good Bye, ICPC, IOI, online mirror, or special named contest but the contest group or round number is unclear, ask the user before publishing.

If the contest kind is unclear, ask the user whether to place it as regular numeric, `Educational`, or `Others`.

### Codeforces Combined Rounds

Some Codeforces Div. 1 + Div. 2 rounds share problems under different contest IDs and problem labels, for example a Div. 2 `A` can be the same problem as a Div. 1 `C`.

When reliable metadata says the submitted solution corresponds to multiple Codeforces contest/problem pairs, publish the same solution to every target path.

Represent the targets as pairs:

```text
contest_id=<contest id>, round_number=<round number>, contest_group=<contest group for Others>, problem_id=<problem id>
```

Apply the normal Codeforces path rule to each pair:

```text
<target_base>/<hundreds_bucket>/<tens_bucket>/<round_number>/<problem_id>_<problem_title_slug>.<ext>
```

Example:

| Shared problem mapping | Target paths below `target_base` |
| --- | --- |
| Div. 2 `2188A` == Div. 1 `2187C`, both from Codeforces Round `1077`, title `Example Title` | `1000/1070/1077/A_Example_Title.cpp` and `1000/1070/1077/C_Example_Title.cpp` |

For multiple targets, copy the source solution to each target path. Do not move the source into only one target when more than one target is required.

Do not guess the paired Div. 1 or Div. 2 target from contest naming alone. Require reliable evidence such as:

- An explicit user instruction, for example "also publish this as Div. 1 C".
- Source metadata comments listing both contest/problem pairs.
- A problem URL or known mapping source that clearly identifies both pairs.

If a round appears combined but the paired contest/problem ID is unclear, ask the user before publishing.

## Ambiguity Rules

Ask the user before moving or copying files when any of these are true:

- The source filename is weak, such as `a.cpp`, `main.py`, `solution.cpp`, or `solve.rs`.
- Multiple candidate solution files are plausible.
- The platform cannot be determined confidently.
- The contest ID or problem ID cannot be determined confidently.
- The Codeforces round number cannot be determined confidently.
- The Codeforces contest kind cannot be determined confidently.
- A Codeforces problem may belong to a combined Div. 1 + Div. 2 round but the paired target is unclear.
- The AtCoder or Codeforces problem title cannot be determined confidently.
- The target path already exists.
- The language extension is unknown.

The confirmation should show:

```text
source: <source path>
platform: <atcoder|codeforces>
contest_id: <contest id>
round_number: <round number, for Codeforces path placement>
contest_group: <contest group, for Codeforces Others>
problem_id: <problem id>
contest_kind: <regular|Educational|Others, for Codeforces>
problem_title: <problem title>
target: <target path>
additional_targets: <extra target paths, for Codeforces combined rounds>
```

Do not publish until the user confirms ambiguous metadata.

## Collision Rules

If the target path does not exist, create parent directories as needed and move or copy the file.

If the target path exists:

- Treat it as an update only when the user explicitly intended to update that exact solution.
- Otherwise, stop and ask whether to overwrite, keep both, or cancel.
- Never overwrite silently.

If keeping both, ask for the desired suffix or filename. Do not invent a duplicate naming scheme without confirmation.
