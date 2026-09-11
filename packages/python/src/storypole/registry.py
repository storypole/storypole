"""The registry store: locating the repo, reading and writing feature files,
locks, impact acknowledgement, and the health check.

Operations return a Result rather than printing. The CLI decides whether that
becomes prose on a terminal or JSON on a pipe -- but the *rule* lives here, so
it holds however the caller is driven.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass

from .model import (
    ACTIVE, BODY_SECTIONS, CLAIMABLE_PHASE, LEGACY_STATUS, PHASES, TERMINAL,
    Feature, gate, parse_feature, phase_index, section_filled,
)

DEFAULT_CONFIG = {
    "wip_limit": 6,
    "lock_stale_days": 7,
    "integration_branch": "main",
    "repo_url": "",
    "app_url": "",
    "run_cmd": "",
    "test_cmd": "",
}


@dataclass
class Result:
    ok: bool
    message: str = ""
    fix: str = ""
    data: dict | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def blocked(message: str, fix: str, **data) -> Result:
    return Result(False, message, fix, data or None)


def done(message: str, **data) -> Result:
    return Result(True, message, "", data or None)


# --- locating things ---------------------------------------------------------

def repo_root(start: str | None = None) -> str:
    here = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(here, "features")) or os.path.isdir(
            os.path.join(here, ".storypole")
        ):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return os.path.abspath(start or os.getcwd())
        here = parent


def features_dir(root: str) -> str:
    return os.path.join(root, "features")


def state_dir(root: str) -> str:
    path = os.path.join(root, ".storypole")
    os.makedirs(path, exist_ok=True)
    return path


def load_config(root: str) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = os.path.join(root, ".storypole", "config.json")
    if os.path.exists(path):
        try:
            cfg.update(json.load(open(path, encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return cfg


def save_config(root: str, cfg: dict) -> None:
    with open(os.path.join(state_dir(root), "config.json"), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def load_all(root: str) -> list:
    d = features_dir(root)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith(".md") and not name.startswith("_"):
            path = os.path.join(d, name)
            out.append(parse_feature(open(path, encoding="utf-8").read(), path))
    return out


def find(features: list, fid: str):
    fid = (fid or "").upper()
    for f in features:
        if f.id.upper() == fid:
            return f
    return None


def save(feat: Feature, root: str) -> str:
    feat.updated = dt.date.today().isoformat()
    if not feat.path:
        os.makedirs(features_dir(root), exist_ok=True)
        feat.path = os.path.join(features_dir(root), "%s-%s.md" % (feat.id, feat.slug))
    with open(feat.path, "w", encoding="utf-8") as fh:
        fh.write(feat.render())
    return feat.path


def next_id(features: list) -> str:
    nums = [int(m.group(1)) for f in features if (m := re.match(r"F-(\d+)$", f.id))]
    return "F-%03d" % ((max(nums) + 1) if nums else 1)


def audit(root: str, action: str, actor: str, detail: str) -> None:
    with open(os.path.join(state_dir(root), "audit.log"), "a", encoding="utf-8") as fh:
        fh.write("%s\t%s\t%s\t%s\n" % (
            dt.datetime.now().isoformat(timespec="seconds"), actor or "-", action, detail))


def prd_is_current(root: str) -> bool:
    prd = os.path.join(root, "PRD.md")
    features = load_all(root)
    if not features:
        return True
    if not os.path.exists(prd):
        return False
    return os.path.getmtime(prd) >= max(os.path.getmtime(f.path) for f in features)


def bump_version(version: str, level: str) -> str:
    parts = (version or "0.1.0").split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        major, minor, patch = (int(p) for p in parts[:3])
    except ValueError:
        major, minor, patch = 0, 1, 0
    if level == "major":
        return "%d.0.0" % (major + 1)
    if level == "patch":
        return "%d.%d.%d" % (major, minor, patch + 1)
    return "%d.%d.0" % (major, minor + 1)


# --- impact acknowledgement --------------------------------------------------

def _ack_path(root: str) -> str:
    return os.path.join(state_dir(root), "impact-ack.json")


def load_acks(root: str) -> dict:
    try:
        return json.load(open(_ack_path(root), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record_ack(root: str, feat: Feature, features: list, actor: str) -> None:
    acks = load_acks(root)
    acks[feat.id] = {"fingerprint": feat.fingerprint(features), "actor": actor,
                     "at": dt.datetime.now().isoformat(timespec="seconds")}
    with open(_ack_path(root), "w", encoding="utf-8") as fh:
        json.dump(acks, fh, indent=2)


def ack_is_current(root: str, feat: Feature, features: list) -> bool:
    ack = load_acks(root).get(feat.id)
    return bool(ack and ack.get("fingerprint") == feat.fingerprint(features))


# --- guards ------------------------------------------------------------------

def guard_lock(feat: Feature, actor: str):
    if feat.locked and feat.locked_by != actor:
        age = feat.lock_age_days()
        return blocked(
            "%s is locked by %s%s" % (
                feat.id, feat.locked_by, " (%d days old)" % age if age is not None else ""),
            "Ask %s to unlock it, or `storypole force-unlock %s --as <you> "
            "--reason ...` if they are unreachable. Force-unlock is audited."
            % (feat.locked_by, feat.id),
            id=feat.id, locked_by=feat.locked_by, lock_age_days=age)
    return None


def guard_owner(feat: Feature, actor: str, verb: str = "change"):
    if feat.owner and feat.owner != actor:
        return blocked(
            "%s is owned by %s" % (feat.id, feat.owner),
            "Only the owner may %s it. Agree a handoff with %s, or pick something "
            "from `storypole list --available`." % (verb, feat.owner),
            id=feat.id, owner=feat.owner)
    return None


def blocking_deps(feat: Feature, features: list) -> list:
    return [d for d in feat.depends_on
            if (dep := find(features, d)) and dep.phase not in TERMINAL]


def availability(feat: Feature, features: list) -> dict:
    blockers = blocking_deps(feat, features)
    return {
        "available": (feat.is_active and not feat.locked and not feat.owner
                      and not blockers),
        "blocked_by": blockers,
    }


# --- health check ------------------------------------------------------------

def check(root: str) -> list:
    features = load_all(root)
    cfg = load_config(root)
    problems = []

    def add(kind, message, fix, fid=""):
        problems.append({"kind": kind, "id": fid, "message": message, "fix": fix})

    building = [f for f in features if f.phase == "building"]
    if len(building) > cfg["wip_limit"]:
        add("wip", "%d features in development, limit is %d"
            % (len(building), cfg["wip_limit"]),
            "Integrate or retire something before starting more. A WIP limit that "
            "never bites is not a limit.")

    for f in features:
        if f.phase not in PHASES:
            add("bad-phase", "%s has unknown phase %r" % (f.id, f.phase),
                "Use one of: %s" % ", ".join(PHASES), f.id)
            continue
        if f.phase == "building" and not f.owner:
            add("unowned", "%s is in development with no owner" % f.id,
                "Claim it, or move it back with `storypole set-phase %s --to defined`."
                % f.id, f.id)
        for dep in f.depends_on:
            d = find(features, dep)
            if not d:
                add("broken-dep", "%s depends on %s, which does not exist" % (f.id, dep),
                    "Fix the id or remove the dependency.", f.id)
            elif d.phase == "retired":
                add("retired-dep", "%s depends on %s, which was retired" % (f.id, dep),
                    "Reconcile %s -- its premise may be gone." % f.id, f.id)
        age = f.lock_age_days()
        if f.locked and age is not None and age > cfg["lock_stale_days"]:
            add("stale-lock", "%s locked by %s for %d days" % (f.id, f.locked_by, age),
                "Ask %s, or `storypole force-unlock %s --as <you> --reason ...`"
                % (f.locked_by, f.id), f.id)
        if f.phase == "retired" and not f.retired_reason:
            add("silent-retire", "%s is retired with no reason recorded" % f.id,
                "Add retired_reason, or nobody will remember why and someone will "
                "re-propose it.", f.id)
        if f.phase in ("released", "retired") and not f.learning:
            add("no-learning", "%s left validation with no recorded learning" % f.id,
                "You built it to find something out. Record what: "
                "`storypole learn %s --text \"...\"`." % f.id, f.id)
        if f.expired() and f.is_active:
            add("expired-spike", "%s expired on %s and is still open" % (f.id, f.expires),
                "Answer the question and retire it, or extend the box deliberately. "
                "A spike that quietly becomes permanent work is a spike that failed.",
                f.id)

    if features and not prd_is_current(root):
        add("stale-prd", "PRD.md is missing or older than the feature files",
            "Run: storypole prd build")
    return problems
