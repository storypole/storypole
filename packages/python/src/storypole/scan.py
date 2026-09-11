"""Crawl a running app: route inventory, design tokens, screenshots, smoke tests.

Writes routes.json, DESIGN-SYSTEM.md (tokens ranked by occurrence -- a colour on
twelve pages is a token, a colour used once is drift) and a full-page screenshot
per route.

What it cannot do is tell you what any of it is *for*. A scan enumerates the
current implementation and recovers no intent, so a PRD generated from a scan
alone is a confident restatement of whatever the code already does -- which then
justifies whatever the code already does. Bootstrap must end in an interview.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from urllib.parse import urljoin, urlparse

PLAYWRIGHT_HINT = """
Playwright is not installed, so this scan cannot run. Either:

  pip install playwright && playwright install chromium

or scan by hand -- open each route, and for each one record: the path, what a
user can do there, anything visibly broken, and the colours and fonts in use.
Write the result into .storypole/scan/routes.json yourself; the format is
documented at the top of this file. A manual pass over six routes takes about
twenty minutes and is a perfectly good substitute.
""".strip()

# The sandboxes these agents run in commonly route all traffic through an HTTP
# proxy, which then refuses to resolve localhost -- so a dev server that curl
# reaches fine is unreachable from the browser. Bypass the proxy for local
# hosts rather than making every user rediscover this.
LOCAL_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1", "*.local"]


def is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local")


def apply_proxy_bypass(url: str) -> None:
    if not is_local(url):
        return
    existing = os.environ.get("NO_PROXY", "")
    merged = ",".join(sorted(set(filter(None, existing.split(",") + LOCAL_HOSTS))))
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


TOKEN_JS = r"""
() => {
  const seen = {colors: {}, backgrounds: {}, fonts: {}, sizes: {}, radii: {}, spacing: {}};
  const bump = (bag, key) => { if (!key) return; bag[key] = (bag[key] || 0) + 1; };
  const vars = {};
  for (const sheet of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }   // cross-origin
    for (const rule of Array.from(rules || [])) {
      if (!rule.style) continue;
      for (const prop of Array.from(rule.style)) {
        if (prop.startsWith('--')) vars[prop] = rule.style.getPropertyValue(prop).trim();
      }
    }
  }
  const nodes = Array.from(document.querySelectorAll('body *')).slice(0, 1500);
  for (const el of nodes) {
    const s = getComputedStyle(el);
    bump(seen.colors, s.color);
    if (s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)')
      bump(seen.backgrounds, s.backgroundColor);
    bump(seen.fonts, s.fontFamily);
    bump(seen.sizes, s.fontSize);
    if (s.borderRadius && s.borderRadius !== '0px') bump(seen.radii, s.borderRadius);
    for (const p of ['paddingTop', 'marginTop']) {
      const v = s[p];
      if (v && v !== '0px') bump(seen.spacing, v);
    }
  }
  const surface = {
    links: Array.from(document.querySelectorAll('a[href]')).map(a => ({
      text: (a.innerText || '').trim().slice(0, 60), href: a.getAttribute('href')
    })).slice(0, 200),
    buttons: Array.from(document.querySelectorAll(
      'button, [role=button], input[type=submit]'
    )).map(b => (b.innerText || b.value || '').trim().slice(0, 60)).filter(Boolean).slice(0, 100),
    inputs: Array.from(document.querySelectorAll('input, textarea, select')).map(i => ({
      type: i.getAttribute('type') || i.tagName.toLowerCase(),
      name: i.getAttribute('name') || i.getAttribute('id') || '',
      label: (i.labels && i.labels[0] ? i.labels[0].innerText : '').trim().slice(0, 60)
    })).slice(0, 100),
    headings: Array.from(document.querySelectorAll('h1, h2')).map(
      h => (h.innerText || '').trim().slice(0, 80)
    ).filter(Boolean).slice(0, 30)
  };
  const bodyText = (document.body.innerText || '');
  const errorish = (bodyText.match(
    /(?:^|\n)[^\n]{0,120}(error|not found|failed|exception|undefined|traceback)[^\n]{0,120}/gi
  ) || []).slice(0, 5).map(s => s.trim());
  return {vars, seen, surface, title: document.title, errorish};
}
"""


def rank(bag: dict, limit: int = 12):
    return sorted(bag.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def scan(base: str, out_dir: str, max_pages: int, smoke: bool, timeout: int) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(PLAYWRIGHT_HINT, file=sys.stderr)
        raise SystemExit(3)

    apply_proxy_bypass(base)
    shots = os.path.join(out_dir, "screenshots")
    os.makedirs(shots, exist_ok=True)

    origin = "{0.scheme}://{0.netloc}".format(urlparse(base))
    queue, seen, routes = [base], set(), []
    totals = {k: collections.Counter() for k in
              ("colors", "backgrounds", "fonts", "sizes", "radii", "spacing")}
    css_vars: dict = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                  ignore_https_errors=True)
        page = ctx.new_page()
        console_errors: list = []
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" else None)

        while queue and len(routes) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            console_errors.clear()
            entry = {"url": url, "path": urlparse(url).path or "/"}
            try:
                resp = page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(400)
                entry["status"] = resp.status if resp else None
            except Exception as exc:                      # noqa: BLE001
                entry["status"] = None
                entry["error"] = str(exc).splitlines()[0][:200]
                routes.append(entry)
                continue

            try:
                data = page.evaluate(TOKEN_JS)
            except Exception as exc:                      # noqa: BLE001
                entry["error"] = "evaluate failed: %s" % str(exc)[:150]
                routes.append(entry)
                continue

            entry["title"] = data["title"]
            entry["surface"] = data["surface"]
            entry["console_errors"] = list(console_errors)
            entry["visible_errors"] = data["errorish"]
            for key, bag in data["seen"].items():
                totals[key].update(bag)
            css_vars.update(data["vars"])

            name = re.sub(r"[^a-z0-9]+", "-", entry["path"].lower()).strip("-") or "index"
            shot = os.path.join(shots, "%s.png" % name[:60])
            try:
                page.screenshot(path=shot, full_page=True)
                entry["screenshot"] = os.path.relpath(shot, out_dir)
            except Exception:                             # noqa: BLE001
                pass

            for link in data["surface"]["links"]:
                href = link.get("href") or ""
                if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                nxt = urljoin(url, href).split("#")[0]
                if nxt.startswith(origin) and nxt not in seen:
                    queue.append(nxt)

            routes.append(entry)

        browser.close()

    result = {
        "base": base,
        "routes": routes,
        "css_vars": css_vars,
        "tokens": {k: rank(v) for k, v in totals.items()},
        "smoke": smoke,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "routes.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    write_design_system(result, out_dir)
    return result


def write_design_system(result: dict, out_dir: str) -> None:
    lines = [
        "# Design system (observed)",
        "",
        "Generated by `scan_app.py` from %d route(s) of %s."
        % (len(result["routes"]), result["base"]),
        "",
        "Ranked by occurrence. Frequency is the signal: a colour appearing on "
        "twelve pages is a token; a colour appearing once is drift, and worth "
        "asking about before it is enshrined.",
        "",
    ]
    if result["css_vars"]:
        lines += ["## Authored custom properties", "",
                  "These were declared deliberately -- trust them over the "
                  "computed values below.", "",
                  "| Property | Value |", "| --- | --- |"]
        for k, v in sorted(result["css_vars"].items()):
            lines.append("| `%s` | `%s` |" % (k, v))
        lines.append("")

    titles = {
        "colors": "Text colours", "backgrounds": "Background colours",
        "fonts": "Font stacks", "sizes": "Font sizes",
        "radii": "Border radii", "spacing": "Spacing steps",
    }
    for key, title in titles.items():
        entries = result["tokens"].get(key) or []
        if not entries:
            continue
        lines += ["## %s" % title, "", "| Value | Occurrences |", "| --- | --- |"]
        for value, count in entries:
            lines.append("| `%s` | %d |" % (value, count))
        lines.append("")
    with open(os.path.join(out_dir, "DESIGN-SYSTEM.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def report(result: dict) -> int:
    routes = result["routes"]
    print("Scanned %d route(s) of %s\n" % (len(routes), result["base"]))
    bad = 0
    for r in routes:
        flags = []
        if r.get("status") and r["status"] >= 400:
            flags.append("HTTP %s" % r["status"])
        if r.get("error"):
            flags.append(r["error"])
        if r.get("console_errors"):
            flags.append("%d console error(s)" % len(r["console_errors"]))
        if r.get("visible_errors"):
            flags.append("error text on page")
        if flags:
            bad += 1
        print("  %-28s %-40s %s" % (r["path"], (r.get("title") or "")[:40],
                                    "; ".join(flags) or "ok"))
    print("\n%d route(s) with problems." % bad)
    if result["smoke"] and bad:
        print("\nSmoke mode: exiting 1 because routes are failing.", file=sys.stderr)
        return 1
    return 0
