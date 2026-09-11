"""The `storypole` command."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import emit as emit_mod
from . import hooks, ops, prd
from . import registry as rg
from .help_topics import QUICKSTART, TOPICS, topic_list
from .model import PHASES, PHASE_LABEL, phase_index
from .registry import Result

__version__ = "0.1.0"


def _emit(result: Result, as_json: bool, human=None) -> int:
    """Guidance goes to stderr so it survives being piped; data to stdout."""
    if as_json:
        payload = {"ok": result.ok}
        if result.data:
            payload.update(result.data)
        if not result.ok:
            payload.update({"error": result.message, "fix": result.fix})
        elif result.message:
            payload["message"] = result.message
        print(json.dumps(payload, indent=2))
    elif result.ok:
        if human:
            human(result)
        elif result.message:
            print(result.message)
    if not result.ok:
        print("BLOCKED: %s" % result.message, file=sys.stderr)
        if result.fix:
            print("  -> %s" % result.fix, file=sys.stderr)
    return result.exit_code


def _print_list(result: Result) -> None:
    rows = result.data["features"]
    if not rows:
        print("No features match.")
        return
    width = max(len(r["title"]) for r in rows)
    for r in rows:
        marks = []
        if r["locked_by"]:
            marks.append("locked by %s" % r["locked_by"])
        if r["blocked_by"]:
            marks.append("blocked on %s" % ",".join(r["blocked_by"]))
        if r["available"]:
            marks.append("available")
        if r["expires"]:
            marks.append("expires %s" % r["expires"])
        print("%-7s %-*s  %-11s %-10s %-7s %s"
              % (r["id"], width, r["title"], PHASE_LABEL.get(r["phase"], r["phase"]),
                 r["owner"] or "-", r["version"], "; ".join(marks)))


def _print_impact(result: Result) -> None:
    d = result.data
    print("Impact of changing %s (%s)\n" % (d["id"], d["title"]))
    if d["depends_on"]:
        print("  depends on : %s" % ", ".join(d["depends_on"]))
    if not d["dependents"]:
        print("  No other feature declares a dependency on this one.")
    else:
        print("  %d feature(s) depend on it:" % len(d["dependents"]))
        for f in d["dependents"]:
            print("    %-7s %-30s owner %s (%s)"
                  % (f["id"], f["title"], f["owner"] or "-", f["phase"]))
        print("\nBefore bumping, confirm each dependent's acceptance criteria still "
              "hold.\nIf one does not, amend that feature too.", file=sys.stderr)


def cmd_check(root: str, as_json: bool, strict: bool) -> int:
    problems = rg.check(root)
    if as_json:
        print(json.dumps({"ok": not problems, "count": len(problems),
                          "problems": problems}, indent=2))
    elif not problems:
        print("check: clean")
    else:
        for p in problems:
            print("  [%s] %s" % (p["kind"], p["message"]))
            print("        -> %s" % p["fix"])
        print("\n%d problem(s)." % len(problems))
    return 1 if (problems and strict) else 0


def cmd_scan(args) -> int:
    from . import scan as scan_mod
    if not scan_mod.is_local(args.url):
        print("Scanning a non-local host. If this is production, stop and ask for a "
              "staging URL: do not submit forms or click destructive controls "
              "against real data.", file=sys.stderr)
    result = scan_mod.scan(args.url, args.out, args.max_pages, args.smoke, args.timeout)
    print("Wrote %s/routes.json and %s/DESIGN-SYSTEM.md\n" % (args.out, args.out))
    return scan_mod.report(result)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="storypole",
        description="A shared reference for a team building one prototype. "
                    "Run `storypole quickstart` if this is your first time.",
        epilog="Every command takes --json. Exit codes: 0 proceed, 1 blocked.")
    p.add_argument("--version", action="version", version="storypole %s" % __version__)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--root", default=None, help="repo root (default: auto-detect)")
    sub = p.add_subparsers(dest="cmd")

    def actor(sp):
        sp.add_argument("--as", dest="actor", default=os.environ.get("STORYPOLE_USER", ""),
                        help="who is acting (or $STORYPOLE_USER)")

    sub.add_parser("quickstart", help="five-minute onboarding -- start here")
    sp = sub.add_parser("help", help="explain a topic: %s" % ", ".join(sorted(TOPICS)))
    sp.add_argument("topic", nargs="?", default="")

    sub.add_parser("init", help="create features/, changelog.d/ and config")

    sp = sub.add_parser("new", help="add a feature")
    sp.add_argument("--title", required=True); sp.add_argument("--owner", default="")
    sp.add_argument("--id", default=None); sp.add_argument("--priority", default="p2")
    sp.add_argument("--depends-on", nargs="*", dest="depends_on")
    sp.add_argument("--expires", default="", help="kill date for a time-boxed spike")

    sp = sub.add_parser("list", help="list features")
    sp.add_argument("--phase", choices=PHASES); sp.add_argument("--owner")
    sp.add_argument("--available", action="store_true",
                    help="only unowned, unlocked, unblocked features")

    sp = sub.add_parser("show", help="print one feature"); sp.add_argument("id")

    sp = sub.add_parser("claim", help="take ownership")
    sp.add_argument("id"); actor(sp); sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("advance", help="move to the next phase (gated)")
    sp.add_argument("id"); actor(sp); sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("set-phase", help="move to a specific phase (gated)")
    sp.add_argument("id"); sp.add_argument("--to", required=True, choices=PHASES)
    actor(sp); sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("lock", help="lock a feature you own"); sp.add_argument("id"); actor(sp)
    sp = sub.add_parser("unlock", help="release your own lock"); sp.add_argument("id"); actor(sp)
    sp = sub.add_parser("force-unlock", help="break someone else's lock (audited)")
    sp.add_argument("id"); actor(sp); sp.add_argument("--reason", default="")

    sp = sub.add_parser("impact", help="list dependents -- required before bump")
    sp.add_argument("id"); actor(sp)

    sp = sub.add_parser("bump", help="bump a feature version")
    sp.add_argument("id"); actor(sp)
    sp.add_argument("--level", choices=["major", "minor", "patch"], default="minor")

    sp = sub.add_parser("smoke", help="record a smoke-test result")
    sp.add_argument("id"); actor(sp)
    sp.add_argument("--result", required=True, choices=["pass", "fail"])

    sp = sub.add_parser("learn", help="record what you found out")
    sp.add_argument("id"); actor(sp); sp.add_argument("--text", default="")

    sp = sub.add_parser("drop", help="retire a feature, with a reason")
    sp.add_argument("id"); actor(sp); sp.add_argument("--reason", default="")
    sp.add_argument("--learning", default=""); sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("check", help="registry health")
    sp.add_argument("--strict", action="store_true", help="exit 1 on any problem")

    sp = sub.add_parser("migrate", help="move pre-phase-model files onto phases")
    actor(sp)

    sp = sub.add_parser("prd", help="generate or verify PRD.md")
    sp.add_argument("action", nargs="?", default="build", choices=["build", "check"])
    sp.add_argument("--out", default=None)

    sp = sub.add_parser("scan", help="crawl a running app")
    sp.add_argument("url"); sp.add_argument("--out", default=".storypole/scan")
    sp.add_argument("--max-pages", type=int, default=25)
    sp.add_argument("--timeout", type=int, default=15000)
    sp.add_argument("--smoke", action="store_true", help="exit 1 if any route errors")

    sp = sub.add_parser("emit", help="generate PROTOCOL.md and agent instruction files")
    sp.add_argument("--to", nargs="*", dest="targets",
                    help="targets: %s" % ", ".join(emit_mod.TARGETS))
    sp.add_argument("--ci", action="store_true",
                    help="also write the CI workflow and a CODEOWNERS template")

    sp = sub.add_parser("install-hooks", help="install the pre-commit hook")
    sp.add_argument("--uninstall", action="store_true")
    sp.add_argument("--print", dest="print_only", action="store_true")

    sp = sub.add_parser("guard-staged", help=argparse.SUPPRESS)   # used by the hook
    actor(sp); sp.add_argument("paths", nargs="*")

    for spx in sub.choices.values():
        spx.add_argument("--json", action="store_true",
                         default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return p


NEEDS_ACTOR = {"claim", "lock", "unlock", "force-unlock", "bump", "drop",
               "advance", "set-phase", "smoke", "learn"}


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        print(QUICKSTART.strip())
        return 0
    if args.cmd == "quickstart":
        print(QUICKSTART.strip())
        return 0
    if args.cmd == "help":
        if not args.topic or args.topic == "topics":
            print("Topics:\n")
            print(topic_list())
            print("\n  storypole help <topic>")
            return 0
        if args.topic not in TOPICS:
            print("No topic %r. Try:\n\n%s" % (args.topic, topic_list()), file=sys.stderr)
            return 2
        print(TOPICS[args.topic].strip())
        return 0

    root = os.path.abspath(args.root) if args.root else rg.repo_root()
    as_json = getattr(args, "json", False)

    if args.cmd in NEEDS_ACTOR and not args.actor:
        return _emit(rg.blocked(
            "no actor given",
            "Pass --as <name>, or set STORYPOLE_USER in your shell. Attribution "
            "matters when four people each have an agent committing."), as_json)

    if args.cmd == "init":
        return _emit(ops.init(root), as_json)
    if args.cmd == "new":
        return _emit(ops.new(root, args.title, args.owner, args.id, args.priority,
                             args.depends_on, args.expires), as_json)
    if args.cmd == "list":
        return _emit(ops.listing(root, args.phase or "", args.owner or "",
                                 args.available), as_json, _print_list)
    if args.cmd == "show":
        r = ops.show(root, args.id)
        if r.ok and not as_json:
            print(open(r.data["feature"]["path"], encoding="utf-8").read())
            return 0
        return _emit(r, as_json)
    if args.cmd == "claim":
        return _emit(ops.claim(root, args.id, args.actor, args.force), as_json)
    if args.cmd == "advance":
        return _emit(ops.advance(root, args.id, args.actor, args.force), as_json)
    if args.cmd == "set-phase":
        return _emit(ops.set_phase(root, args.id, getattr(args, "to"), args.actor,
                                   args.force), as_json)
    if args.cmd == "lock":
        return _emit(ops.lock(root, args.id, args.actor), as_json)
    if args.cmd == "unlock":
        return _emit(ops.unlock(root, args.id, args.actor), as_json)
    if args.cmd == "force-unlock":
        return _emit(ops.force_unlock(root, args.id, args.actor, args.reason), as_json)
    if args.cmd == "impact":
        return _emit(ops.impact(root, args.id, args.actor), as_json, _print_impact)
    if args.cmd == "bump":
        return _emit(ops.bump(root, args.id, args.actor, args.level), as_json)
    if args.cmd == "smoke":
        return _emit(ops.smoke(root, args.id, args.actor, args.result), as_json)
    if args.cmd == "learn":
        return _emit(ops.learn(root, args.id, args.actor, args.text), as_json)
    if args.cmd == "drop":
        return _emit(ops.drop(root, args.id, args.actor, args.reason, args.learning,
                              args.force), as_json)
    if args.cmd == "migrate":
        return _emit(ops.migrate(root, args.actor), as_json)
    if args.cmd == "check":
        return cmd_check(root, as_json, args.strict)
    if args.cmd == "prd":
        return _emit(prd.build(root, args.out) if args.action == "build"
                     else prd.check(root, args.out), as_json)
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "emit":
        r = emit_mod.emit(root, args.targets)
        if r.ok and args.ci:
            r2 = hooks.write_ci(root)
            r.message += "; " + r2.message
        return _emit(r, as_json)
    if args.cmd == "install-hooks":
        if args.print_only:
            print(hooks.PRE_COMMIT)
            return 0
        return _emit(hooks.install(root, args.uninstall), as_json)
    if args.cmd == "guard-staged":
        return _emit(hooks.guard_staged(root, args.actor, args.paths), as_json)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
