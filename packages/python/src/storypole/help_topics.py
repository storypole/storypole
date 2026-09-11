"""`storypole help <topic>` -- the onboarding a reference doc does not give you.

A teammate who has never seen this will type `storypole` and nothing else.
What they get back has to be enough to start.
"""

QUICKSTART = """
Storypole -- a shared reference for a team building one prototype.

A story pole is a stick a mason marks once at the start of a job. Every
bricklayer works from it, so all their courses land at the same heights.

YOUR FIRST FIVE MINUTES

  1. See what the team is building
       storypole list
  2. Read the spec -- the PRD is generated from these features
       open PRD.md          (start with the intro, then Development)
  3. Read the graveyard in PRD.md. Fastest way to learn what this team
     already knows, and it stops your first idea being one they killed.
  4. Find something free
       storypole list --available
  5. Take it
       storypole claim F-00X --as <your-name>
       storypole lock  F-00X --as <your-name>

  Set STORYPOLE_USER=<your-name> in your shell and drop the --as everywhere.

THE THREE RULES THAT MATTER

  - Spec before code. Amend the feature file, run `impact`, then `bump`,
    then write code. Not the other way round.
  - Additive, never a replacement. Contribute a delta to the current head.
    Do not regenerate the prototype in your own style.
  - Do not refactor code you did not come to change.

WHEN SOMETHING REFUSES

  Every refusal tells you how to fix it. Read the "->" line. Exit code 1
  means blocked, 0 means proceed.

  storypole help topics        what else you can read
"""

TOPICS = {
    "phases": """
PHASES

  discovery -> defined -> designing -> building -> validating -> released
                                                              -> retired

  A feature enters a phase only when that phase's artifact exists. That is
  what turns the phase field from a label into a lifecycle.

    defined      needs a Problem section
    designing    needs Requirements
    building     needs an owner, Acceptance criteria, and Out of scope
    validating   needs a passing smoke test and a current PRD
    released     needs a recorded learning
    retired      needs a reason and a learning

  Move one step:     storypole advance F-002 --as sam
  Jump deliberately: storypole set-phase F-002 --to designing --as sam
  Override a gate:   add --force, and be able to say why.
""",
    "locks": """
LOCKS

  A lock is an exclusive claim on a feature while you are changing it.
  Nobody else can enhance, bump, advance or retire it.

    storypole lock   F-002 --as sam
    storypole unlock F-002 --as sam

  Lock only what you are actively changing; unlock as soon as you are done.
  A lock is a courtesy to five other people, not a parking space.

  If someone is unreachable:

    storypole force-unlock F-002 --as you --reason "priya on leave, demo Thu"

  That is audited to .storypole/audit.log. Tell the person. A broken lock
  discovered by surprise is how a team stops trusting the convention and
  starts editing frontmatter by hand -- at which point none of this works.

  The lock is a convention, not a security boundary. For real enforcement:
  storypole emit --ci writes a CODEOWNERS template; pair it with branch
  protection.
""",
    "impact": """
IMPACT

  Before bumping a feature you must run:

    storypole impact F-002 --as sam

  It lists every feature that declares a dependency on this one. Read it,
  and for each dependent answer out loud: does its acceptance criteria still
  hold? If one does not, amend that feature too. A PRD asserting two things
  that cannot both be true is worse than no PRD.

  `bump` refuses until this has run against the feature's current state.
  The rule is in the tool rather than the instructions, so it holds even
  when a weaker agent or a hurried human is driving.

  What impact will NOT catch: contradictory requirements that are each fine
  alone -- one person specs autosave, another an explicit save button. Both
  pass review; they collide at integration. The only defence is that people
  read the in-progress section of the PRD before starting.
""",
    "release": """
RELEASE

  Feature versions live in each feature file and bump freely. The
  prototype's release version is assigned AT RELEASE, never on a branch --
  otherwise three people each claim v0.5.0 in parallel and someone loses.

  At release:
    1. Fold changelog.d/*.md into CHANGELOG.md, then delete the fragments.
    2. Tag the repo.
    3. Advance shipped features to released (each needs a learning).
    4. storypole prd build && git commit

  Write changelog fragments as you go -- one new file per contribution.
  Never append to a shared changelog: new files do not merge-conflict, and
  six people appending to one file always do.
""",
    "spikes": """
SPIKES

  Prototype work is often not a feature -- it is "spend two days finding
  out if this is possible." A spike needs a kill criterion and an expiry
  date, not acceptance criteria.

    storypole new --title "Can we sync 500 photos over 3G?" --expires 2026-09-18

  Put the question and the kill criterion in Requirements. When it expires,
  retire it with the answer:

    storypole drop F-009 --as sam --reason "answered" \\
      --learning "50 photos took 38s on 3G -- batching required"

  `storypole check` flags expired spikes still open. A spike that quietly
  becomes permanent unowned work is a spike that failed.
""",
    "enforcement": """
ENFORCEMENT

  Instructions ask an agent to comply. Claude will; a weaker agent will
  not, and neither will a human in a hurry. Push the rules down:

    storypole install-hooks     pre-commit: refuses commits touching a
                                feature locked by someone else, or leaving
                                PRD.md stale
    storypole emit --ci         GitHub Actions running check --strict and
                                prd check, plus a CODEOWNERS template

  Be clear-eyed about the layers:
    - The hook is skippable with --no-verify. It is a seatbelt.
    - CI blocks a merge, which is real, but only on PRs.
    - CODEOWNERS + branch protection is the only enforcement that cannot
      be bypassed locally, because it runs on the server.
""",
    "agents": """
AGENT INSTRUCTION FILES

  PROTOCOL.md is the tool-agnostic source of truth. Every per-tool file is
  generated from it:

    storypole emit                 all targets
    storypole emit --to agents claude cursor

  Targets: agents (AGENTS.md), claude (CLAUDE.md), cursor, windsurf,
  copilot, gemini, cline.

  Never hand-maintain those files. Six instruction files edited by hand
  drift within a week, and then each teammate's agent follows a different
  protocol -- the exact failure the registry exists to prevent, one level
  up. Edit PROTOCOL.md (in emit.py) and re-emit.
""",
    "bootstrap": """
BOOTSTRAP (organizer, once)

  Before the team starts, one person generates the first PRD from the
  running app:

    storypole init
    storypole scan http://localhost:3000

  The scan writes a route inventory, per-route screenshots and a
  DESIGN-SYSTEM.md ranked by occurrence frequency. It also flags failing
  routes, which is how you tell shipped from half-built.

  Then cluster routes into 5-15 features -- a feature is a capability a
  user would name, not a route and not a component.

  A scan tells you what an app does. It cannot tell you what it is FOR.
  Nothing in the DOM says why a screen exists. So bootstrap must end in an
  interview with whoever owns the prototype, and the PRD must mark what is
  observed fact versus their stated intent. A PRD built from a scan alone
  just restates the current implementation, and then justifies it.

  If the app is in production, ask for a staging URL. Do not submit forms
  or click destructive controls against real data.
""",
}


def topic_list() -> str:
    return "\n".join("  %-14s %s" % (name, text.strip().splitlines()[0].lower())
                     for name, text in sorted(TOPICS.items()))
