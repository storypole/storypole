"""The operations. Each returns a Result; none of them print."""

from __future__ import annotations

import datetime as dt
import os

from .model import (
    ACTIVE, BODY_SECTIONS, PHASES, TERMINAL, Feature, gate, phase_index,
)
from . import registry as rg
from .registry import Result, blocked, done


def _template_body() -> str:
    return "\n".join("## %s\n\n_%s_\n" % (h, hint) for h, hint in BODY_SECTIONS)


def init(root: str) -> Result:
    os.makedirs(rg.features_dir(root), exist_ok=True)
    os.makedirs(os.path.join(root, "changelog.d"), exist_ok=True)
    cfg_path = os.path.join(rg.state_dir(root), "config.json")
    if not os.path.exists(cfg_path):
        rg.save_config(root, dict(rg.DEFAULT_CONFIG))
    intro = os.path.join(root, "PRD-intro.md")
    if not os.path.exists(intro):
        with open(intro, "w", encoding="utf-8") as fh:
            fh.write("# Overview\n\n_Written by hand -- the only prose in the PRD a "
                     "human owns. Say what this prototype is for, who it is for, and "
                     "what would make it a success in six weeks._\n")
    return done("Initialised Storypole in %s" % root, root=root)


def new(root: str, title: str, owner: str = "", fid: str | None = None,
        priority: str = "p2", depends_on=None, expires: str = "") -> Result:
    features = rg.load_all(root)
    fid = fid or rg.next_id(features)
    if rg.find(features, fid):
        return blocked("%s already exists" % fid, "Pick another id, or omit --id.")
    feat = Feature(id=fid, title=title, owner=owner, phase="discovery",
                   priority=priority, depends_on=list(depends_on or []),
                   expires=expires, created=dt.date.today().isoformat(),
                   body=_template_body())
    path = rg.save(feat, root)
    rg.audit(root, "new", owner, "%s %s" % (fid, title))
    return done("Created %s -> %s" % (fid, path), id=fid, path=path, phase="discovery")


def listing(root: str, phase: str = "", owner: str = "", available: bool = False) -> Result:
    features = rg.load_all(root)
    cfg = rg.load_config(root)
    rows = []
    for f in features:
        if phase and f.phase != phase:
            continue
        if owner and f.owner != owner:
            continue
        avail = rg.availability(f, features)
        if available and not avail["available"]:
            continue
        rows.append(dict(id=f.id, title=f.title, phase=f.phase, owner=f.owner,
                         locked_by=f.locked_by, version=f.version,
                         priority=f.priority, depends_on=f.depends_on,
                         expires=f.expires, **avail))
    rows.sort(key=lambda r: (r["priority"], phase_index(r["phase"]), r["id"]))
    return done("", features=rows, wip_limit=cfg["wip_limit"])


def show(root: str, fid: str) -> Result:
    feat = rg.find(rg.load_all(root), fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    return done("", feature=dict(feat.to_meta(), body=feat.body, path=feat.path))


def claim(root: str, fid: str, actor: str, force: bool = False) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if r := rg.guard_lock(feat, actor):
        return r
    if r := rg.guard_owner(feat, actor, "claim"):
        return r
    cfg = rg.load_config(root)
    mine = [f for f in features if f.owner == actor and f.phase == "building"]
    if len(mine) >= cfg["wip_limit"]:
        return blocked("WIP limit reached (%d in development)" % len(mine),
                       "Finish or retire one of %s first."
                       % ", ".join(f.id for f in mine))
    blockers = rg.blocking_deps(feat, features)
    if blockers and not force:
        return blocked("%s depends on unfinished work: %s" % (feat.id, ", ".join(blockers)),
                       "Ship the dependency first, or pass --force if you are "
                       "deliberately building against it in parallel.",
                       blocked_by=blockers)
    feat.owner = actor
    rg.save(feat, root)
    rg.audit(root, "claim", actor, feat.id)
    return done("%s claimed by %s (phase: %s)" % (feat.id, actor, feat.phase),
                id=feat.id, owner=actor, phase=feat.phase)


def set_phase(root: str, fid: str, target: str, actor: str,
              force: bool = False) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if target not in PHASES:
        return blocked("unknown phase %r" % target, "Use one of: %s" % ", ".join(PHASES))
    if r := rg.guard_lock(feat, actor):
        return r
    if r := rg.guard_owner(feat, actor, "advance"):
        return r
    if phase_index(target) > phase_index(feat.phase) and not force:
        # entering a phase requires every gate between here and there
        for step in PHASES[phase_index(feat.phase) + 1: phase_index(target) + 1]:
            if g := gate(feat, step, rg.prd_is_current(root)):
                return blocked("%s cannot enter %s: %s" % (feat.id, step, g[0]), g[1],
                               id=feat.id, from_phase=feat.phase, to_phase=step)
    old = feat.phase
    feat.phase = target
    rg.save(feat, root)
    rg.audit(root, "phase", actor, "%s %s -> %s%s"
             % (feat.id, old, target, " (forced)" if force else ""))
    return done("%s %s -> %s" % (feat.id, old, target),
                id=feat.id, **{"from": old, "to": target})


def advance(root: str, fid: str, actor: str, force: bool = False) -> Result:
    feat = rg.find(rg.load_all(root), fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    idx = phase_index(feat.phase)
    if idx >= len(PHASES) - 2:
        return blocked("%s is at %s and cannot advance further" % (feat.id, feat.phase),
                       "Retire it with `storypole drop %s --as <you> --reason ...` "
                       "if it is done." % feat.id)
    return set_phase(root, fid, PHASES[idx + 1], actor, force)


def lock(root: str, fid: str, actor: str) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if feat.locked:
        if feat.locked_by == actor:
            return done("%s is already locked by you." % feat.id, id=feat.id)
        return rg.guard_lock(feat, actor)
    if r := rg.guard_owner(feat, actor, "lock"):
        return r
    feat.locked_by = actor
    feat.locked_at = dt.date.today().isoformat()
    feat.owner = feat.owner or actor
    rg.save(feat, root)
    rg.audit(root, "lock", actor, feat.id)
    return done("%s locked by %s" % (feat.id, actor), id=feat.id, locked_by=actor)


def unlock(root: str, fid: str, actor: str) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if not feat.locked:
        return done("%s is not locked." % feat.id, id=feat.id)
    if feat.locked_by != actor:
        return rg.guard_lock(feat, actor)
    feat.locked_by = ""
    feat.locked_at = ""
    rg.save(feat, root)
    rg.audit(root, "unlock", actor, feat.id)
    return done("%s unlocked" % feat.id, id=feat.id)


def force_unlock(root: str, fid: str, actor: str, reason: str) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if not feat.locked:
        return done("%s is not locked." % feat.id, id=feat.id)
    if not reason:
        return blocked("force-unlock requires --reason",
                       "Say why the lock is being broken. It goes in the audit log "
                       "with your name.")
    previous = feat.locked_by
    feat.locked_by = ""
    feat.locked_at = ""
    rg.save(feat, root)
    rg.audit(root, "force-unlock", actor, "%s (was %s): %s" % (feat.id, previous, reason))
    return done("%s force-unlocked (was %s). Logged." % (feat.id, previous),
                id=feat.id, previous_holder=previous, reason=reason)


def impact(root: str, fid: str, actor: str) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    dependents = [f for f in features if feat.id in f.depends_on]
    rg.record_ack(root, feat, features, actor)
    return done("", id=feat.id, title=feat.title,
                depends_on=[d for d in feat.depends_on if rg.find(features, d)],
                dependents=[dict(id=f.id, title=f.title, owner=f.owner, phase=f.phase)
                            for f in dependents],
                acknowledged=True)


def bump(root: str, fid: str, actor: str, level: str = "minor") -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if r := rg.guard_lock(feat, actor):
        return r
    if r := rg.guard_owner(feat, actor, "bump"):
        return r
    if not rg.ack_is_current(root, feat, features):
        return blocked(
            "impact analysis has not been run for %s at its current state" % feat.id,
            "Run `storypole impact %s --as %s` first, read the dependents it lists, "
            "and confirm their acceptance criteria still hold." % (feat.id, actor))
    old = feat.version
    feat.version = rg.bump_version(old, level)
    rg.save(feat, root)
    rg.audit(root, "bump", actor, "%s %s -> %s" % (feat.id, old, feat.version))
    return done("%s %s -> %s" % (feat.id, old, feat.version),
                id=feat.id, **{"from": old, "to": feat.version})


def smoke(root: str, fid: str, actor: str, result: str) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if result not in ("pass", "fail"):
        return blocked("--result must be pass or fail", "Record what actually happened.")
    feat.smoke = result
    rg.save(feat, root)
    rg.audit(root, "smoke", actor, "%s %s" % (feat.id, result))
    return done("%s smoke test recorded: %s" % (feat.id, result), id=feat.id, smoke=result)


def learn(root: str, fid: str, actor: str, text: str) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if not text:
        return blocked("--text is required", "Say what you found out. One sentence.")
    feat.learning = text
    rg.save(feat, root)
    rg.audit(root, "learn", actor, "%s: %s" % (feat.id, text[:80]))
    return done("%s learning recorded." % feat.id, id=feat.id, learning=text)


def drop(root: str, fid: str, actor: str, reason: str, learning: str = "",
         force: bool = False) -> Result:
    features = rg.load_all(root)
    feat = rg.find(features, fid)
    if not feat:
        return blocked("no such feature %s" % fid, "Run `storypole list` to see ids.")
    if r := rg.guard_lock(feat, actor):
        return r
    if not reason:
        return blocked("drop requires --reason",
                       "Record why it died. Without it someone re-proposes the same "
                       "idea in three weeks. The graveyard is the most valuable part "
                       "of a prototype PRD.")
    dependents = [f.id for f in features if feat.id in f.depends_on and f.is_active]
    if dependents and not force:
        return blocked("%s still has active dependents: %s" % (feat.id, ", ".join(dependents)),
                       "Update or retire those first, or pass --force if you have "
                       "already reconciled them.", dependents=dependents)
    feat.phase = "retired"
    feat.retired_reason = reason
    feat.learning = learning or feat.learning
    feat.locked_by = ""
    feat.locked_at = ""
    rg.save(feat, root)
    rg.audit(root, "retire", actor, "%s: %s" % (feat.id, reason))
    return done("%s retired: %s" % (feat.id, reason), id=feat.id, reason=reason)


def migrate(root: str, actor: str = "") -> Result:
    """Move pre-phase-model feature files onto the phase set, in place."""
    changed = []
    for feat in rg.load_all(root):
        raw = open(feat.path, encoding="utf-8").read()
        if "\nphase:" in raw.split("\n---", 2)[0] + "\n":
            continue
        rg.save(feat, root)          # parse_feature already mapped status -> phase
        changed.append({"id": feat.id, "phase": feat.phase})
    if changed:
        rg.audit(root, "migrate", actor, "%d feature(s)" % len(changed))
    return done("Migrated %d feature file(s) to the phase model." % len(changed),
                migrated=changed)
