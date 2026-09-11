"""Enforcement: git hooks, CI, and CODEOWNERS.

Instructions ask an agent to comply. Claude will; a weaker agent will not, and
neither will a human in a hurry. Pushing the rules down into a pre-commit hook
and a CI check makes agent compliance stop being load-bearing -- any tool that
can run bash gets the guarantees for free.

The honest limit: a local hook is skippable with --no-verify. Only CODEOWNERS
plus branch protection is real enforcement, because it runs on the server.
"""

from __future__ import annotations

import os
import subprocess

from . import registry as rg

PRE_COMMIT = r'''#!/bin/sh
# Installed by `storypole install-hooks`. Remove with `storypole install-hooks --uninstall`.
#
# Refuses a commit that touches a feature file locked by someone else, or that
# leaves PRD.md stale. Skippable with --no-verify: this is a seatbelt, not a
# lock. Real enforcement is CODEOWNERS + branch protection.

STORYPOLE_USER="${STORYPOLE_USER:-$(git config user.name)}"
export STORYPOLE_USER

staged=$(git diff --cached --name-only --diff-filter=ACM | grep '^features/' || true)
if [ -n "$staged" ]; then
  if ! storypole guard-staged --as "$STORYPOLE_USER" $staged; then
    echo "" >&2
    echo "Commit refused by storypole. Use --no-verify only if you know why." >&2
    exit 1
  fi
fi

if ! storypole prd check >/dev/null 2>&1; then
  echo "PRD.md is out of date with features/. Run: storypole prd build" >&2
  exit 1
fi
exit 0
'''

CI_WORKFLOW = '''name: storypole

on:
  pull_request:
  push:
    branches: [%(branch)s]

jobs:
  registry:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install storypole
      - name: Registry health
        run: storypole check --strict
      - name: PRD is current
        run: storypole prd check
'''

CODEOWNERS = '''# Storypole: feature specs are the shared reference, so changes to them get
# reviewed. Replace @your-org/prototype-team with a real team.
#
# This is the only enforcement that actually holds -- pair it with branch
# protection ("Require review from Code Owners") on %(branch)s, or the locks
# remain an honour system.

/features/      @your-org/prototype-team
/PRD-intro.md   @your-org/prototype-team
'''


def guard_staged(root: str, actor: str, paths: list) -> rg.Result:
    """Refuse staged edits to features locked by someone else."""
    features = {f.path: f for f in rg.load_all(root)}
    offences = []
    for rel in paths:
        full = os.path.abspath(os.path.join(root, rel))
        feat = features.get(full)
        if not feat:
            continue
        if feat.locked and feat.locked_by != actor:
            offences.append({"id": feat.id, "path": rel, "locked_by": feat.locked_by})
    if offences:
        who = ", ".join("%s (locked by %s)" % (o["id"], o["locked_by"]) for o in offences)
        return rg.blocked(
            "staged changes touch features locked by someone else: %s" % who,
            "Ask the lock holder, or `storypole force-unlock <id> --as %s "
            "--reason ...`. Editing frontmatter by hand to get around a lock is "
            "how the convention dies for everyone." % (actor or "<you>"),
            offences=offences)
    return rg.done("No locked features touched.", checked=len(paths))


def install(root: str, uninstall: bool = False) -> rg.Result:
    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        return rg.blocked("not a git repository", "Run this from your repo root.")
    hook = os.path.join(git_dir, "hooks", "pre-commit")
    if uninstall:
        if os.path.exists(hook) and "storypole" in open(hook, encoding="utf-8").read():
            os.remove(hook)
            return rg.done("Removed %s" % hook)
        return rg.done("No storypole pre-commit hook installed.")
    if os.path.exists(hook) and "storypole" not in open(hook, encoding="utf-8").read():
        return rg.blocked(
            "a pre-commit hook already exists and is not ours",
            "Merge the snippet in by hand rather than clobbering it. "
            "Print it with `storypole install-hooks --print`.")
    os.makedirs(os.path.dirname(hook), exist_ok=True)
    with open(hook, "w", encoding="utf-8") as fh:
        fh.write(PRE_COMMIT)
    os.chmod(hook, 0o755)
    return rg.done("Installed %s" % hook, path=hook)


def write_ci(root: str) -> rg.Result:
    cfg = rg.load_config(root)
    branch = cfg.get("integration_branch") or "main"
    written = []
    wf_dir = os.path.join(root, ".github", "workflows")
    os.makedirs(wf_dir, exist_ok=True)
    wf = os.path.join(wf_dir, "storypole.yml")
    with open(wf, "w", encoding="utf-8") as fh:
        fh.write(CI_WORKFLOW % {"branch": branch})
    written.append(wf)
    co = os.path.join(root, ".github", "CODEOWNERS")
    if not os.path.exists(co):
        with open(co, "w", encoding="utf-8") as fh:
            fh.write(CODEOWNERS % {"branch": branch})
        written.append(co)
    return rg.done("Wrote %s" % ", ".join(os.path.relpath(p, root) for p in written),
                   written=written)
