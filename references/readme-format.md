# README Format

Use this format for AtCoder and Codeforces contest folder `README.md` files.

## File Location

Create or update `README.md` in the contest folder that contains the solution file.

Examples:

```text
<target_base>/ABC/400/420/422/README.md
<target_base>/AHC/0/40/43/README.md
<target_base>/PAST/202309-open/README.md
<target_base>/1900/1910/1917/README.md
<target_base>/Educational/1900/1900/1900/README.md
<target_base>/Others/1900/1910/1917/README.md
```

For Codeforces combined Div. 1 + Div. 2 problems with multiple target contest folders, update the `README.md` in every target contest folder.

## Header

The first line must be the contest link:

```text
# <contest_url>
```

Use the canonical contest URL for the folder being updated.

Examples:

```text
# https://atcoder.jp/contests/abc422
# https://codeforces.com/contest/2061
```

## Entry Format

Each problem entry must use this exact shape:

```text
<problem_id> / Rating : $<rating>$ / <Tag1>, <Tag2>
```

Rules:

- `problem_id`: uppercase Codeforces problem index, preserving digits, for example `A`, `A1`, `B2`, `C`.
- For AtCoder, use the uppercase task label such as `A`, `B`, `C`, or `Ex`.
- `rating`: use the Codeforces `Problem.rating` value from metadata when available.
- For AtCoder, use the estimated difficulty from Kenkoooo AtCoder Problems `problem-models.json` when available.
- If rating is unknown, absent, or unavailable, write `$-$`.
- Tags must follow `references/solution-tags.md`.
- Put one blank line after the header and one blank line between problem entries.
- Do not use tables, bullets, or extra prose.

## Codeforces Example

```markdown
# https://codeforces.com/contest/2061

A / Rating : $800$ / Case_Work

B / Rating : $1100$ / Math, Greedy

C / Rating : $1600$ / DP

D / Rating : $1600$ / DP, Ad_Hoc

E / Rating : $2000$ / Bruteforce, Sorting, Greedy, Bit_Mask
```

## AtCoder Example

```markdown
# https://atcoder.jp/contests/abc422

A / Rating : $-$ / Case_Work

B / Rating : $450$ / Math, Greedy

C / Rating : $1200$ / DP
```

## Updating Existing README Files

If `README.md` does not exist, create it with the header and the new problem entry.

If `README.md` exists:

- Preserve the header if it already matches the contest URL.
- Fix the header if the contest ID is clearly the same folder contest.
- Update an existing line for the same `problem_id` instead of duplicating it.
- Insert new entries in natural Codeforces problem order when practical.
- Preserve existing entries that are unrelated to the current publish operation.

Natural order examples:

```text
A, A1, A2, B, C, D, E, F
```

## Tag Inference

Read `references/solution-tags.md` before writing tags.

Infer tags from the solution implementation. Official Codeforces tags may be used as supporting context, but do not copy them blindly if the submitted code uses a narrower or different technique.

If tag inference is uncertain, ask the user before updating the README.
