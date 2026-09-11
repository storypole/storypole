#!/usr/bin/env node
// STORYPOLE_NPM_LAUNCHER -- marker used to recognise other copies of this file.
//
// Launcher. Storypole is implemented in Python -- this package exists so that
// `npx @storypole/skill` works for teams whose muscle memory is npm, not pip.
//
// It does not vendor a copy of the tool: two implementations of the same rules
// would drift, which is the exact failure the registry exists to prevent.
//
// The bin is named `storypole`, the same as the real CLI, so a naive PATH
// lookup finds this launcher itself and recurses. Every candidate is therefore
// checked: skip our own file, skip any other copy of this launcher (global
// install + npx cache), and refuse to re-enter from a child launcher.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const MARKER = "STORYPOLE_NPM_LAUNCHER";
const GUARD = "STORYPOLE_LAUNCHER_ACTIVE";
const args = process.argv.slice(2);

function realpath(p) {
  try {
    return fs.realpathSync(p);
  } catch {
    return p;
  }
}

function isLauncher(file) {
  try {
    const fd = fs.openSync(file, "r");
    const buf = Buffer.alloc(512);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    fs.closeSync(fd);
    return buf.subarray(0, n).toString("utf8").includes(MARKER);
  } catch {
    return false;
  }
}

function findRealCli() {
  const self = realpath(process.argv[1]);
  const exts = process.platform === "win32"
    ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";").map((e) => e.toLowerCase())
    : [""];
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    if (!dir) continue;
    for (const ext of exts) {
      const candidate = path.join(dir, "storypole" + ext);
      let stat;
      try {
        stat = fs.statSync(candidate);
      } catch {
        continue;
      }
      if (!stat.isFile()) continue;
      const resolved = realpath(candidate);
      if (resolved === self || isLauncher(resolved)) continue;
      return candidate;
    }
  }
  return null;
}

function exitWith(result) {
  if (result.error) {
    process.stderr.write(`storypole launcher: ${result.error.message}\n`);
    process.exit(1);
  }
  process.exit(result.status === null ? 1 : result.status);
}

const childEnv = { ...process.env, [GUARD]: "1" };

// 1. A real storypole binary on PATH -- covers pipx, which isolates the package
//    so that no python on PATH can import it.
if (process.env[GUARD] !== "1") {
  const cli = findRealCli();
  if (cli) {
    exitWith(spawnSync(cli, args, { stdio: "inherit", env: childEnv }));
  }
}

// 2. A python that can import the package -- covers `pip install` into an
//    environment whose bin directory is not on PATH.
for (const exe of ["python3", "python"]) {
  const probe = spawnSync(exe, ["-c", "import storypole.cli"], { stdio: "ignore" });
  if (probe.status === 0) {
    exitWith(spawnSync(exe, ["-m", "storypole.cli", ...args], {
      stdio: "inherit",
      env: childEnv,
    }));
  }
}

process.stderr.write(
  [
    "storypole is not installed.",
    "",
    "This package is a launcher; the tool itself is a Python package.",
    "Install it with either:",
    "",
    "  pipx install storypole      (recommended -- isolated, on your PATH)",
    "  pip install storypole",
    "",
    "Python 3.9 or newer is required.",
    "",
  ].join("\n"),
);
process.exit(127);
