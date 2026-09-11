# Bootstrap mode

Read this only when `features/` is empty or missing. One person — the organizer
who owns the prototype — runs this once. Team collaboration does not begin
until it is finished and they have approved the result.

## The thing to be clear-eyed about first

**A scan tells you what an app does. It cannot tell you what it is for.**

Routes, components, form fields and design tokens are all recoverable from a
running app. Intent is not. Nothing in the DOM will tell you that reports exist
because engineers currently text photos to a foreman who loses them.

So a PRD generated from a scan alone is a confident restatement of the current
implementation — which then silently justifies whatever the code already does.
That is the failure mode most likely to bite here, which is why bootstrap
**ends in an interview**, and why the generated PRD marks every claim as either
observed fact or the organizer's stated intent. Do not blur those two.

## 1. Get a URL you are allowed to scan

Ask where the app is running. **If it is production, ask for a staging URL
instead.** If there is no staging environment, scan read-only: do not submit
forms, do not click anything destructive, and say plainly that coverage will be
partial as a result. Ask for credentials if the app is behind a login.

## 2. Scan it

```bash
storypole scan $APP_URL --out .storypole/scan
```

This writes `routes.json`, `DESIGN-SYSTEM.md`, and a full-page screenshot per
route. If Playwright is not installed the script says so and describes the
manual alternative — a hand walkthrough of six routes takes about twenty
minutes and is a perfectly good substitute. Do not fake a scan you did not run.

Scanning a local dev server from inside a sandbox often fails where `curl`
succeeds, because the sandbox proxy will not resolve localhost. The script
bypasses the proxy for local hosts already; if it still fails, that is the
first thing to check.

## 3. Read what came back

Three things matter in `routes.json`:

- **Route inventory** — what exists, and what each route lets a user do.
- **Failures** — non-200 status, console errors, error text visible on the
  page. This is how you distinguish *released* from *half-built*: a route that
  renders an exception is in-progress, whatever anyone says.
- **Design tokens**, ranked by frequency. A colour on twelve pages is a token;
  a colour used once is drift. An unstyled page showing a default serif font is
  worth surfacing, not smoothing over.

## 4. Cluster routes into features

This is a judgment call and the part most likely to need tuning. A feature is a
capability a user would name, not a route and not a component. Three routes
that together let someone file a report are **one** feature.

Aim for 5–15 features on a first pass. Fewer than five and they are too coarse
to own separately; more than twenty and the registry becomes a component list,
which nobody will maintain.

Create them:

```bash
storypole new --title "File a defect report" --owner ""
```

Set `phase: released` for what demonstrably works, `building` for anything
the scan showed erroring or half-built. Leave `owner` empty — ownership is
claimed by the team, not assigned by the bootstrap.

## 5. Interview the organizer

Non-negotiable. The scan gave you the *what*; only they have the *why*. Ask,
and stop guessing when you do not know:

1. What is this prototype for, and who is it for? What are they doing today
   instead?
2. What would make it a success — what has to be true in six weeks?
3. For each feature I found: is this intentional, a leftover, or a stub?
4. What is missing that I could not see? Anything unbuilt is a feature too.
5. Which of these matter most? Priority makes "what should I pick up?"
   answerable.
6. What is explicitly out of scope? This prevents six people relitigating it.

Where they are unsure, ask rather than filling the gap. A feature file that
says "owner to confirm" is more useful than a confident invention.

## 6. Write the intro and generate the PRD

Put their answers to Q1 and Q2 into `PRD-intro.md` — that file is hand-written
and is the only prose in the PRD that a human owns. Everything else is
generated:

```bash
storypole prd build
storypole check
```

## 7. Hand it back for approval

Show the organizer the PRD and be explicit about which parts are observed and
which are their stated intent. Ask them to correct the clustering — they will
want to split or merge something, and it is far cheaper now than after six
people have claimed features.

Then commit, and the team can begin:

```bash
git add features/ PRD.md PRD-intro.md .storypole/ && \
  git commit -m "Bootstrap Storypole registry from $APP_URL"
```
