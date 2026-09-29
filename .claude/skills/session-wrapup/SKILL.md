---
name: session-wrapup
description: Close out a work session so the next one starts cold in seconds — update the TODO/backlog, write or refresh a handoff doc for multi-session campaigns, sync living docs the session made stale, and propose the final commit. Use when the user invokes /session-wrapup, says "wrap up", "create a handoff file for the next session", "document your progress/findings for another session", "update the relevant docs before we stop", or is clearly ending a session mid-campaign. The counterpart bootstrap ("what's next / where did we leave off") should read what this skill writes.
---

# Session wrap-up

"Where did we leave off?" costs a re-orientation every session it isn't answered in a file.
This skill makes the answer a file. Priority order: the repo's TODO is the index, the
handoff doc is the deep context, living docs must not lie.

## 1. Take stock

From this session: what shipped (commits), what's in flight (uncommitted work — list it
honestly), what was decided (and why), what was deferred or discovered. Check
`git status` — stranded WIP is the #1 thing lost between sessions.

## 2. Update the TODO/backlog

Mark done items done (so they're never re-proposed), add new items with a one-line "why" and
a date. Keep it a *backlog*, not a log: completed-item narratives belong in the handoff doc
or commit history — prune Done sections that have grown into an archive.

## 3. Handoff doc (multi-session campaigns only)

If the work continues across sessions, write/refresh a dated handoff doc — in this repo use
`_templates/session-handoff.md` if it exists, else mirror its sections: **State / Done /
Next (sequenced) / Open questions / Gotchas / Verification commands**. The test: a fresh
session reading only this doc can start the next item without asking anything. Update the
existing campaign doc in place rather than spawning a second one.

For single-session tasks, skip the doc — the TODO line and commit message are enough.

## 4. Sync living docs

Anything this session made stale: CLAUDE.md/AGENTS.md claims, architecture maps, runbooks,
README. Only touch what actually drifted.

## 5. Final commit proposal

Present the commit set (including the handoff/TODO edits) and a one-line "next session
starts with: …". Wait for the user's "commit" if that's the house habit; commit directly if
the session's pattern was autonomous.
