---
name: storypole
description: Coordinate several people contributing to one prototype or working app, through a git-backed feature registry with owner locks, PDLC phase gates, and a generated PRD. Use when contributing a feature to a shared prototype, claiming or locking work, advancing a feature's phase, killing a feature, cutting a release, or bootstrapping a PRD from a running app URL.
---

# Storypole

A story pole is a stick a mason marks once at the start of a job. Every
bricklayer on the wall works from it, so all their courses land at exactly the
same heights. This is that, for a team building one prototype: a single shared
reference, many people working in parallel, no drift.

## Setup

```bash
pipx install storypole      # or: pip install storypole
storypole --version
```

If it is not installed, install it before doing anything else — do not
hand-roll the operations, and do not edit feature frontmatter directly. The
rules live in the tool so they hold for everyone, including contributors whose
agent never reads this file.

Config lives in `.storypole/config.json` (`storypole init` creates it):
`integration_branch`, `app_url`, `run_cmd`, `test_cmd`, `wip_limit`,
`lock_stale_days`, `repo_url`.

Identify who you are acting for with `--as <name>`, or set `STORYPOLE_USER`.
Attribution matters: four people each have an agent committing, and "Claude did
it" is not an owner.

## Route: which mode are you in?

**Check `features/` before anything else.**

- **Empty or missing** → bootstrap mode. The organizer is setting up. Read
  `references/bootstrap.md` and follow it. Team collaboration does not begin
  until a first PRD exists and the organizer has approved it.
- **Populated** → contribution mode. Continue below.

Do not load `references/bootstrap.md` in contribution mode, or
`references/lifecycle.md` unless the task is one it covers.

## Contribution mode

### 1. Read the current state first

```bash
git checkout $INTEGRATION_BRANCH && git pull
storypole list
storypole check
```

Never start from a stale base. If `check` reports problems, say so — do not
silently work around them.

### 2. Decide what the contributor is doing

```bash
storypole list --available
```

`--available` means unowned, unlocked, and not blocked on unfinished
dependencies. Then establish which of three things they want:

- **Pick up a pending feature** → claim it.
- **Enhance an existing feature** → check the lock first.
- **Propose something new** → `storypole new`, then write the spec before any
  code.

If they name a feature that is locked, stop and say who holds it. A locked
feature cannot be enhanced, bumped, advanced or retired by anyone else. Never
edit frontmatter by hand to get around this — the moment one person does, the
convention is dead for everyone.

### 3. Claim and lock

```bash
storypole claim F-002 --as sam
storypole lock  F-002 --as sam
```

Lock only what you are actively changing, and unlock as soon as you are done. A
lock is a courtesy to five other people, not a parking space.

### 4. Amend the spec before writing code

Edit `features/F-002-*.md` — requirements, acceptance criteria, and an explicit
out-of-scope section. Then:

```bash
storypole impact F-002 --as sam
```

This lists every feature that declares a dependency on this one. Read it. For
each dependent, answer out loud: *does its acceptance criteria still hold?* If
one does not, amend that feature too. A PRD asserting two things that cannot
both be true is worse than no PRD.

`bump` refuses until `impact` has run against the feature's current state. That
rule is in the tool, not in these instructions, so it holds even when a weaker
agent or a hurried human is driving.

```bash
storypole bump F-002 --as sam --level minor
storypole prd build
```

### 5. Advance the phase

```bash
storypole advance F-002 --as sam
```

Phases run `discovery → defined → designing → building → validating → released`,
with `retired` as the exit at any point. Each transition is gated on the
previous phase's artifact actually existing — an owner and acceptance criteria
before development, a passing smoke test and a current PRD before validation, a
recorded learning before release. Run `storypole help phases` for the full set.

When a gate refuses, **write the missing artifact**. Do not reach for `--force`
to get past it; that is available for deliberate exceptions you can justify, not
for skipping the work.

### 6. Now write the code

Two rules, and the second is the one that keeps six contributions composable:

- **Additive to the current head, never a replacement of it.** Do not
  regenerate the prototype in your own style. Six people each doing that gives
  you six divergent forks and no prototype.
- **Do not refactor code you did not come to change.** Not naming, not
  formatting, not "while I was in here". It will feel restrictive. It is the
  single highest-value constraint here — a diff touching only the feature under
  change is reviewable by the five people who did not write it.

### 7. Record the change

Write a new file in `changelog.d/` — never append to a shared changelog. New
files do not merge-conflict; six people appending to one file always do.

```
changelog.d/F-002-sam-offline-queue.md

- **F-002 Offline queue** (sam) — queue writes while offline and replay on
  reconnect. Adds a retry table; no change to the upload API.
```

### 8. Validate, then open the PR

```bash
storypole scan $APP_URL --smoke
storypole smoke F-002 --result pass --as sam
storypole check --strict
storypole prd check
$RUN_TESTS
```

All must pass. Push a branch, open a PR against `$INTEGRATION_BRANCH`, then
unlock when it merges:

```bash
storypole unlock F-002 --as sam
```

## Versioning

Feature versions live in each feature file and bump freely. **The prototype's
release version is assigned at release, never on a branch** — otherwise three
people each claim v0.5.0 in parallel and someone loses. At release: fold
`changelog.d/` into `CHANGELOG.md`, tag, and advance shipped features to
`released` (each needs a recorded learning).

## Enforcement

```bash
storypole install-hooks      # pre-commit: blocks edits to someone else's lock
storypole emit --ci          # CI check + a CODEOWNERS template
storypole emit               # regenerate AGENTS.md, CLAUDE.md, .cursor/rules/, ...
```

`PROTOCOL.md` is the tool-agnostic source of truth; every agent instruction file
is generated from it. Never hand-maintain those — they drift within a week, and
then each teammate's agent follows a different protocol.

## Other situations

`references/lifecycle.md` covers killing a feature, stale locks and
force-unlock, ownership handoff, time-boxed spikes, non-coding contributors,
PRD/code drift, WIP limits, decision logs and demo readiness. Read it when one
of those comes up — not routinely. `storypole help topics` covers the same
ground for a human at a terminal.

## What this does not guarantee

The lock is a convention, not a security boundary. The tool refuses the
operation and a cooperating agent honours it, but anyone can edit frontmatter by
hand, and the pre-commit hook is skippable with `--no-verify`. Only `CODEOWNERS`
on `features/` plus branch protection is real enforcement, because it runs on
the server. Say this out loud to the team rather than letting them assume more
than it delivers.
