"""Feature model, frontmatter parsing, and the PDLC phase machine.

The phase machine is the part worth reading. A status field that anyone can set
to anything is a label; a status field with gates on the transitions is a
lifecycle. Each phase can only be entered once the previous phase's artifact
actually exists, which is what stops "in progress" from meaning six different
things to six people.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field, asdict

# --- the PDLC phases, in order ---------------------------------------------

PHASES = [
    "discovery",    # we think there is a problem here
    "defined",      # requirements and acceptance criteria written
    "designing",    # shape and design tokens settled
    "building",     # code being written
    "validating",   # built, in front of someone, learning
    "released",     # in the prototype, version stamped
    "retired",      # dead, with a reason and a lesson
]
TERMINAL = ("released", "retired")
ACTIVE = tuple(p for p in PHASES if p not in TERMINAL)
CLAIMABLE_PHASE = "building"

# Statuses from before the phase model, and where they land.
LEGACY_STATUS = {
    "proposed": "defined",
    "in-progress": "building",
    "shipped": "released",
    "dropped": "retired",
}

PHASE_LABEL = {
    "discovery": "Discovery",
    "defined": "Defined",
    "designing": "Design",
    "building": "Development",
    "validating": "Validation",
    "released": "Released",
    "retired": "Retired",
}

BODY_SECTIONS = [
    ("Problem", "What is broken or missing, and for whom."),
    ("Requirements", "Numbered, testable statements."),
    ("Acceptance criteria", "How we know it is done."),
    ("Out of scope", "What this deliberately does not do."),
]


def phase_index(phase: str) -> int:
    try:
        return PHASES.index(phase)
    except ValueError:
        return -1


# --- frontmatter ------------------------------------------------------------

def _parse_scalar(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()] if inner else []
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    return raw


def _dump_scalar(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    text = "" if value is None else str(value)
    if text == "" or re.search(r"[:#]", text):
        return '"%s"' % text.replace('"', '\\"')
    return text


def split_frontmatter(text: str):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[3:end].strip("\n").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        meta[key.strip()] = _parse_scalar(raw)
    return meta, text[end + 4 :].lstrip("\n")


def section_text(body: str, name: str) -> str:
    """Return the prose under a `## Name` heading, minus italic placeholders."""
    pattern = re.compile(
        r"^#{1,6}\s+%s\s*$(.*?)(?=^#{1,6}\s|\Z)" % re.escape(name),
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(body)
    if not m:
        return ""
    lines = []
    for line in m.group(1).splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("_") and s.endswith("_"):   # template hint, not content
            continue
        lines.append(s)
    return "\n".join(lines).strip()


def section_filled(body: str, name: str) -> bool:
    return bool(section_text(body, name))


# --- the feature -------------------------------------------------------------

@dataclass
class Feature:
    id: str
    title: str
    phase: str = "discovery"
    owner: str = ""
    locked_by: str = ""
    locked_at: str = ""
    version: str = "0.1.0"
    depends_on: list = field(default_factory=list)
    priority: str = "p2"
    created: str = ""
    updated: str = ""
    smoke: str = ""            # pass | fail | "" (not run)
    learning: str = ""         # required to leave validating
    retired_reason: str = ""
    expires: str = ""          # spikes: a kill date
    body: str = ""
    path: str = ""

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-") or "feature"

    @property
    def locked(self) -> bool:
        return bool(self.locked_by)

    @property
    def is_active(self) -> bool:
        return self.phase in ACTIVE

    def lock_age_days(self):
        if not self.locked_at:
            return None
        try:
            return (dt.date.today() - dt.date.fromisoformat(self.locked_at[:10])).days
        except ValueError:
            return None

    def expired(self) -> bool:
        if not self.expires:
            return False
        try:
            return dt.date.fromisoformat(self.expires[:10]) < dt.date.today()
        except ValueError:
            return False

    def to_meta(self) -> dict:
        d = asdict(self)
        d.pop("body"); d.pop("path")
        return d

    def render(self) -> str:
        order = ["id", "title", "phase", "owner", "locked_by", "locked_at",
                 "version", "depends_on", "priority", "created", "updated",
                 "smoke", "learning", "retired_reason", "expires"]
        meta = self.to_meta()
        lines = ["---"]
        for key in order:
            value = meta.get(key, "")
            if key in ("smoke", "learning", "retired_reason", "expires") and not value:
                continue
            lines.append("%s: %s" % (key, _dump_scalar(value)))
        lines += ["---", "", self.body.rstrip() + "\n"]
        return "\n".join(lines)

    def fingerprint(self, features: list) -> str:
        dependents = sorted(f.id for f in features if self.id in f.depends_on)
        payload = "|".join([self.id, self.version, ",".join(sorted(self.depends_on)),
                            ",".join(dependents)])
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def parse_feature(text: str, path: str = "") -> Feature:
    meta, body = split_frontmatter(text)
    depends = meta.get("depends_on", [])
    if isinstance(depends, str):
        depends = [d for d in re.split(r"[,\s]+", depends) if d]
    phase = str(meta.get("phase") or meta.get("status") or "discovery")
    phase = LEGACY_STATUS.get(phase, phase)
    return Feature(
        id=str(meta.get("id", "")), title=str(meta.get("title", "")), phase=phase,
        owner=str(meta.get("owner", "")), locked_by=str(meta.get("locked_by", "")),
        locked_at=str(meta.get("locked_at", "")),
        version=str(meta.get("version", "0.1.0")), depends_on=depends,
        priority=str(meta.get("priority", "p2")),
        created=str(meta.get("created", "")), updated=str(meta.get("updated", "")),
        smoke=str(meta.get("smoke", "")), learning=str(meta.get("learning", "")),
        retired_reason=str(meta.get("retired_reason") or meta.get("dropped_reason", "")),
        expires=str(meta.get("expires", "")), body=body, path=path,
    )


# --- the gates ---------------------------------------------------------------

def gate(feat: Feature, target: str, prd_current: bool = True):
    """Can `feat` enter `target`? Returns None, or (reason, fix).

    Gates are about artifacts existing, not about anyone's opinion. Each one
    names the thing that must be true and where to write it.
    """
    if target == "defined":
        if not section_filled(feat.body, "Problem"):
            return ("no problem statement",
                    "Write the Problem section in %s -- what is broken, and for whom."
                    % (feat.path or feat.id))
    elif target == "designing":
        if not section_filled(feat.body, "Requirements"):
            return ("no requirements",
                    "Write numbered, testable Requirements in %s." % (feat.path or feat.id))
    elif target == "building":
        if not feat.owner:
            return ("no owner", "Run `storypole claim %s --as <you>` first." % feat.id)
        if not section_filled(feat.body, "Acceptance criteria"):
            return ("no acceptance criteria",
                    "Write Acceptance criteria in %s -- how we know it is done."
                    % (feat.path or feat.id))
        if not section_filled(feat.body, "Out of scope"):
            return ("no out-of-scope section",
                    "State what %s deliberately does not do. This is what stops six "
                    "people relitigating the boundary later." % feat.id)
    elif target == "validating":
        if feat.smoke != "pass":
            return ("no passing smoke test",
                    "Run `storypole scan $APP_URL --smoke`, then record the result: "
                    "`storypole smoke %s --result pass --as <you>`." % feat.id)
        if not prd_current:
            return ("PRD is out of date",
                    "Run `storypole prd build` and commit it before validating.")
    elif target == "released":
        if not feat.learning:
            return ("nothing learned recorded",
                    "You built this to find something out. Record it: "
                    "`storypole learn %s --text \"...\" --as <you>`." % feat.id)
    elif target == "retired":
        if not feat.retired_reason:
            return ("no reason recorded",
                    "Run `storypole drop %s --as <you> --reason \"...\"`." % feat.id)
        if not feat.learning:
            return ("nothing learned recorded",
                    "A retired feature with no lesson is just lost time. "
                    "Add --learning when dropping it.")
    return None
