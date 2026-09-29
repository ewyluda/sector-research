---
name: ship-pr
description: The full PR shipping ritual in one command — review the PR (or all open PRs), verify findings before fixing, apply the fixes, merge, push, delete the branch and worktree, and refresh the repo's living docs. Use when the user invokes /ship-pr, says "review PR #N and merge if it passes", "review any open PRs and merge", "apply the fixes and merge", or after implementation finishes and the branch needs to land. Accepts a PR number, branch name, or nothing (= all open PRs).
---

# Ship PR

Codifies the ritual that used to take four hand-typed prompts per PR: review → fix → merge →
cleanup. The discipline points: findings get *verified* before they're "fixed", and merge is
gated on the review actually passing — "review and merge" never means rubber-stamp.

## 1. Identify

`gh pr list` / `gh pr view <n>` (or the local branch vs main). Note the base branch, CI
status, and whether a worktree backs the branch (`git worktree list`).

## 2. Review

Run the code-review skill on the diff at an effort matching the PR's size and risk. Then
verify each finding against the actual code before treating it as real — reviews produce
plausible-but-wrong findings; reproduce or trace each one (see
superpowers:receiving-code-review if loaded). Partition into: must-fix before merge /
follow-up (log it, don't block) / rejected (say why).

## 3. Fix

Apply must-fix items on the PR branch. Re-run the repo's test/typecheck/build gate after.
If a fix balloons in scope, stop and surface it instead of growing the PR silently.

## 4. Merge & push

Merge per the repo's habit (check git log: merge commits vs squash; default
`gh pr merge --merge`). Push main. Confirm origin is synced (`git status -sb` after fetch).

## 5. Cleanup

Delete the local + remote feature branch and remove any worktree (`git worktree remove`).
Prune stale remote refs. Leave only main unless the user keeps long-lived branches.

## 6. Refresh living docs

If the repo maintains agent/architecture docs (CLAUDE.md, CONTEXT.md, TODO.md,
design/architecture.*, ADRs), update the ones this PR made stale — same commit or a docs
commit right after. Mark the shipped item done in the TODO/campaign doc so no future session
re-proposes it.

## 7. Report

PR link, what was found vs fixed vs deferred (with where the deferrals were logged), test
evidence, and the cleanup state. If anything was skipped (CI red, unverifiable finding),
say so plainly — don't report "merged" as "done" if follow-ups remain.
