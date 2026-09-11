# Storypole

A story pole is a stick a mason marks once at the start of a job. Every
bricklayer on the wall works from it, so all their courses land at exactly the
same heights — one shared reference, many parallel workers, no drift.

Storypole applies that to a team of 5–6 people building one prototype: a
git-backed registry of features, each a markdown file with an owner, a phase and
a lock, from which the PRD is generated rather than hand-written.

## Install

```bash
pipx install storypole      # or: pip install storypole / npx @storypole/skill
storypole quickstart        # five-minute onboarding
```

The npm package is a launcher for the same Python tool — there is deliberately
only one implementation of the rules.

## Bootstrap from a running app

One person runs this once, before the team starts:

```bash
storypole init
storypole scan http://localhost:3000
```

It writes a route inventory, per-route screenshots, and a `DESIGN-SYSTEM.md`
ranked by occurrence frequency, then flags failing routes — which is how you
tell released from half-built. Playwright is optional (`pip install
'storypole[scan]'`); without it the command explains the manual alternative.

A scan tells you what an app does, never what it is *for*, so bootstrap ends in
an interview with whoever owns the prototype.

## Daily use

```bash
storypole list --available          # unowned, unlocked, unblocked
storypole claim   F-002 --as sam
storypole lock    F-002 --as sam
storypole impact  F-002 --as sam    # required before bump
storypole bump    F-002 --as sam
storypole advance F-002 --as sam    # next phase, gated
storypole prd build
```

Set `STORYPOLE_USER` and drop the `--as`. Every command takes `--json`; exit
codes are the contract: `0` proceed, `1` blocked. Guidance goes to stderr, so
the rules reach an agent that never reads an instruction file.

## Phases

```
discovery -> defined -> designing -> building -> validating -> released
                                                            -> retired
```

A feature enters a phase only when that phase's artifact exists: an owner,
acceptance criteria and an out-of-scope section before development; a passing
smoke test and a current PRD before validation; a recorded learning before
release. That is what turns the phase field from a label into a lifecycle.

## Enforcement

```bash
storypole install-hooks     # pre-commit: blocks edits to someone else's lock
storypole emit --ci         # CI check + CODEOWNERS template
storypole emit              # AGENTS.md, CLAUDE.md, .cursor/rules/, ...
```

`PROTOCOL.md` is the tool-agnostic source of truth; every agent instruction file
is generated from it, because six hand-maintained instruction files drift within
a week.

## What it does not guarantee

The lock is a convention, not a security boundary. The tool refuses the
operation and a cooperating agent honours it, but anyone can edit frontmatter by
hand, and the pre-commit hook is skippable with `--no-verify`. Only `CODEOWNERS`
on `features/` plus branch protection is real enforcement, because it runs on
the server.

## Repository layout

```
storypole/            the Claude skill bundle (SKILL.md + references/)
packages/python/      the storypole CLI, published to PyPI
packages/npm/         a launcher, published to npm as @storypole/skill
```

## License

MIT
