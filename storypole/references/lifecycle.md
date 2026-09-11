# Lifecycle: everything that is not the happy path

Phases run `discovery -> defined -> designing -> building -> validating ->
`released`, with `retired` as the exit at any point. Each transition is gated
on the previous phase's artifact existing; `storypole help phases` lists them.

"One person enhances one feature" is maybe a third of what actually happens.
Read the section you need; do not read this file routinely.

## Killing a feature

Prototypes are mostly failed experiments. A registry that only knows how to add
is lying about what the team is doing.

```bash
storypole drop F-004 --as sam \
  --reason "Foremen already text photos; upload adds a step nobody wanted" \
  --learning "Watched 3 users: the friction is retrieval, not capture"
```

`--reason` is mandatory. Without it someone re-proposes the same idea in three
weeks and nobody remembers why it died. **The graveyard is one of the highest-
value things a prototype PRD carries** — it is the difference between a team
that learns and one that circles.

Three things must happen together, or the drop is worse than useless:

1. Mark it retired, with the reason.
2. **Rip out the code.** A retired feature whose code still runs is worse than
   either state alone — the PRD says it is dead and the app says it is alive.
3. Reconcile dependents. `drop` refuses if an active feature depends on it.

`--learning` is optional here but strongly encouraged, and it is the whole
point of a prototype: you built it in order to find something out. Record what
you found out.

## Stale locks

Someone locks a feature and goes on leave. `check` flags any lock older than
`lock_stale_days` (default 7). The escape hatch is deliberate and audited:

```bash
storypole force-unlock F-001 --as sam \
  --reason "priya on leave until the 14th, demo Thursday"
```

It appends to `.storypole/audit.log` with who, when and why. **Tell the person
whose lock you broke.** A broken lock discovered by surprise is exactly how a
team stops trusting the convention and starts hand-editing frontmatter — at
which point none of this works for anybody.

If locks are jamming often, the WIP limit is probably too high, or people are
locking whole features when they are changing one corner.

## Ownership handoff

When someone rotates off, reassign rather than leaving a ghost owner:

```bash
storypole unlock F-002 --as priya
storypole claim  F-002 --as dev
```

`check` flags anything `building` with no owner. An unowned in-progress
feature is the most common way work quietly stops.

## Time-boxed spikes

Prototype work is often not a feature — it is "spend two days finding out if
this is even possible." A spike needs a **kill criterion and an expiry date**,
not acceptance criteria. File it as a feature whose Requirements section says:

```
Spike. Expires 2026-09-18.
Question: can we sync 500 photos over 3G in under a minute?
Kill criterion: if a 50-photo batch takes over 30s, we stop and redesign.
```

When it expires, drop it with the answer in `--learning`. A spike that quietly
becomes permanent unowned work is a spike that failed.

## Dependency ripple

`impact` is mandatory before `bump` — the tool enforces it. But it only catches
what `depends_on` declares. Two things it will not catch:

- **Contradictory requirements that are individually fine.** One person specs
  autosave, another specs an explicit save button. Both pass review alone; they
  collide at integration. This is the classic six-people failure, and the only
  defence is that everyone reads the PRD's in-progress section before starting.
- **Undeclared coupling.** If you discover during implementation that your
  feature touches another, add the `depends_on` edge immediately. Half the
  value of the registry is the edges people bother to record.

## PRD / code drift

Spec-first slows drift; it does not stop it. Every couple of weeks, or before
any demo, reconcile: re-run the scan and ask, feature by feature, does the
running app actually do what the PRD claims?

```bash
storypole scan $APP_URL --out .storypole/scan --smoke
storypole check --strict
```

Where they disagree, the app is the fact and the PRD is the claim. Fix the PRD,
or file the gap as a feature.

## WIP limits and priority

Six people with six in-progress features and no integration is how prototypes
die. `claim` refuses past the limit (default 6, in `.storypole/config.json`).
When it refuses, that is the system working — finish or drop something.

Priority (`p0`–`p3`) makes "what should I pick up?" answerable. Without it,
people take whatever is at the top of the list, which is arbitrary.

## The non-coding contributor

Most 5–6 person prototype teams have a PM or designer with the sharpest ideas
and no branch. They must be able to file and amend features without touching
git. Options, in order of how well they work:

1. They describe the feature to their own agent, which runs `features.py new`
   and opens a PR. Best option: same registry, same rules, no git knowledge.
2. They file an issue; whoever picks it up creates the feature file.
3. Someone pairs with them once a week to file what they have accumulated.

What does not work is letting them describe features only in Slack. Those ideas
are usually the good ones, and they evaporate.

## Feedback intake

People will test the prototype and react. Those reactions need a path into the
registry or they die in a channel nobody searches. Either file each one as a
feature in `discovery`, or attach it to an existing feature's Problem section as
evidence. Prefer evidence over opinion: "three of five testers tried to swipe
here" beats "the nav feels wrong."

## Decision log

Prototypes generate a lot of "we tried X, it didn't work, so we do Y." Lose
that and the seventh person relitigates it. Keep `DECISIONS.md` at the repo
root, append-only, newest first:

```
## 2026-09-04 — Photos upload on reconnect, not immediately
Tried immediate upload; on site 3G a 20-photo batch blocked the UI for 40s.
Decided: queue locally, replay on reconnect. Revisit if we get a better network
assumption.
```

One entry per decision that cost more than an hour to reach.

## Demo readiness

You will cut releases for stakeholder demos, and "which features are actually
demoable" is a different question from "what is released." A half-built feature
behind a flag is released but not demoable.

Before a demo, walk the released list and mark what you would actually show, run
`scan_app.py --smoke` against the demo build, and write the click path down.
Nobody improvises a demo well.

## Onboarding a new joiner

Their first hour, in order:

1. Read `PRD.md` — the intro, then the in-progress section.
2. Read the graveyard. It is the fastest way to learn what this team already
   knows, and it prevents their first suggestion being something you killed.
3. Read `DECISIONS.md`.
4. Run the app locally, and run `features.py list --available`.
5. Claim a `p2`. Not the most interesting thing — the most self-contained one.
