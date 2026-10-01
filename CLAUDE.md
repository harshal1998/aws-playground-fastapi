# Project conventions

## Git workflow

- **Base branch:** `develop`. It is protected: changes land via PR only, with no force-push.
- **Every change starts from an issue.** Create the issue first if there isn't one.

## Issues

- **Title:** Conventional Commits style, `type(scope): <what is wrong / what to do>`, lowercase after the colon, no trailing period.
  - Bugs describe the *problem*: `fix(items): no validation on ItemCreate.price allows negative prices`,
    `fix(s3): exception handlers missing 'raise ... from e' chaining`.
  - Perf/feature work describes the *goal*: `perf(ci): cache Docker layers across CI runs via Buildx + GHA cache`.
  - Types: `fix`, `perf`, `feat`, `chore`, `docs`. Scope is the area touched: `items`, `s3`, `aws`, `portal`, `env`, `ci`, `api`.
- **Body for bugs:**
  ```
  ## Problem
  <what's wrong, where, with a code snippet and the concrete failure>

  ## Fix
  <proposed change>

  ## Files
  - `path/to/file.py`
  ```
- **Body for perf/feature work:** `## Goal`, then `## Plan` (bullets), and optionally `## Expected payoff`, `## Verification` or `## Notes`.
- One problem per issue. Refer to code by repo-relative path in backticks.

## Branches

- `<issue-number>-<short-kebab-case-slug>`, with no type prefix (no `fix/`, `feat/`).
  Examples: `24-speed-up-ci`, `8-dynamodb-attribute-types`, `29-critical-security-fixes`.

## Splitting one issue across several PRs

- **One sub-issue per PR.** Create it with the usual issue conventions, start the body with `Part of #<parent>`,
  and link it with `gh api -X POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<id>`
  (`<id>` is the issue's numeric `id` from `gh api repos/<owner>/<repo>/issues/<n> --jq .id`, not its number).
- **Link with `Fixes`, never `Refs`.** Commits end `Fixes #<sub-issue>`; the PR body starts
  `Fixes #<sub-issue> (part of #<parent>)`. Never write `Fixes #<parent>` in a part: it would close the parent
  while other parts are open. Close the parent by hand once every part has merged.
- **Prefer independent PRs.** Branch each one from `develop` and open it with `--base develop`.
- **Stack only when PR B needs PR A's code.** Branch B from A's branch, open B with `--base <A's branch>`, and
  start its body with `Stacked on #<A> — merge that first`. CI runs on PRs to any base branch.
- **After A merges.** Rebase merges rewrite commits, so B still carries A's old copies. GitHub retargets B to
  `develop`; then `git rebase --onto origin/develop <old A tip> <B branch>`, push with
  `--force-with-lease=<B branch>:<old B sha>`, and re-save B's PR body (`gh pr edit --body-file`) so the issue
  link registers. Force-push PR branches only, never `develop`.
- **Merge one PR at a time.** `develop` requires an up-to-date branch, so after each merge run
  `gh pr update-branch <n> --rebase`, wait for CI, then `gh pr merge <n> --rebase` (rebase merge is the only
  method the repo allows).

## Working style: parallel agents (always, without being asked)

- Always split work across multiple agents running in parallel to speed things up. Don't wait to be asked.
- Give each independent unit its own agent: separate issues, separate files or areas, research or review
  alongside implementation, bulk GitHub operations.
- Agents that change code work in their own git worktree on their own `<issue>-<slug>` branch, so parallel
  edits don't collide. Each opens its own PR, following every convention in this file.
- Keep work sequential only when a step truly depends on the previous one's result. Say which files overlap
  between parallel branches, so merge conflicts are expected.

## Before opening or updating a PR (always, without being asked)

After finishing any implementation, fix or feature:

1. **Self code review.** Review the full diff against `develop` for correctness bugs, edge cases, security,
   and consistency with surrounding code. Fix what you find before pushing.
2. **Impact analysis.** Work out what the change affects: callers and dependents, API/behaviour changes,
   config/env or infra changes, CI/CD effects, migrations or data changes, backward compatibility,
   anything a developer must do after pulling, and the risk and how to roll it back.
3. **Put both in the PR description**, under `## Code review` (what was checked, findings and how each was
   resolved, anything left open) and `## Impact analysis`, alongside the changes and verification sections.

## Commit messages

- **Subject:** `type(scope): imperative summary`, lowercase, no trailing period, same types and scopes as issues.
  Example: `fix(items): reject non-positive prices`.
- **One logical change per commit.** Don't fold unrelated edits (e.g. a CLAUDE.md tweak) into a fix commit.
- **Scope is always present**, including for `docs` and `chore` commits.
- **Body is required** (never subject-only) and is **always a point-wise `- ` bullet list**, never a prose
  paragraph. Put a blank line after the subject. Bullets cover the problem and the concrete changes. Wrap at
  ~72 chars and indent continuation lines by 2 spaces.
- **Footer:** `Fixes #<issue>` on its own line (use `Fixes`, not `Closes`), then the `Co-Authored-By:` trailer when applicable.
- Before committing, check the message against these rules.

```
fix(items): reject non-positive prices

- ItemBase.price accepted zero and negative values with no
  validation, allowing invalid items to be persisted
- Add a Field(gt=0) constraint on price
- Add a regression test covering the 422 rejection

Fixes #5
```
