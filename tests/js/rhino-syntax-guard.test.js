// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Regression guard for device/autojs6's Rhino-engine incompatibilities.
 *
 * AutoJs6's bundled Rhino build (isInterpretedMode, jvm-npm require()) has
 * several gaps that are invisible to tsc and to Node-based unit tests — they
 * only surface as a runtime crash on the actual device. See
 * docs/architecture/components/autojs6.md ("Rhino JS-engine gotchas") for
 * the full incident writeup (stayturgid#34 follow-up investigation). This
 * test catches the two gotchas that are mechanically detectable from the
 * compiled output, so a future PR can't silently reintroduce them:
 *
 *   1. for...of loops — Rhino's interpreted mode throws EvaluatorException
 *      (the iterator protocol isn't implemented for plain arrays there).
 *   2. Duplicate top-level require() local binding names across the whole
 *      require graph — jvm-npm.js doesn't isolate each required file's
 *      top-level scope, so two sibling files (anywhere in the transitive
 *      require graph, not just direct siblings) declaring the same local
 *      name — `const log = require(...)` in two different files, say —
 *      throws "TypeError: redeclaration of var <name>" the moment both
 *      get loaded together, independent of const/let/var.
 *
 * Does NOT catch (no mechanical signal to check):
 *   - The exports/module CommonJS stamp on entry scripts (main.js) —
 *     covered structurally: main.ts uses plain require() calls instead of
 *     `import x = require(...)`, so tsc never emits the stamp for it. If a
 *     future main.ts reintroduces `import`/`export` syntax, this doesn't
 *     re-check that — review main.ts changes by hand for that pattern.
 *   - Java-interop objects lacking JS String.prototype methods until
 *     coerced with String(...) — semantic, would need type information
 *     this test doesn't have.
 */
const fs = require("fs");
const path = require("path");
const repo = path.resolve(__dirname, "..", "..");
const autojs6Root = path.join(repo, "device", "autojs6");
function findJsFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...findJsFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".js")) {
      out.push(full);
    }
  }
  return out.sort();
}
let n = 0;
let failed = 0;
function ok(cond, desc) {
  n++;
  console.log((cond ? "ok " : "not ok ") + n + " - " + desc);
  if (!cond) failed++;
}
const jsFiles = findJsFiles(autojs6Root);
ok(jsFiles.length > 0, "found device/autojs6 compiled .js files to scan (" + jsFiles.length + ")");
// scripts/*.js are standalone diagnostic entry points (each launched on its
// own, never require()'d alongside main.js or each other), so their local
// binding names can't collide with anything — gotcha #2 only applies to
// main.js + lib/*.js, the one real, always-loaded-together require graph.
const productionFiles = jsFiles.filter((f) => {
  const rel = path.relative(autojs6Root, f);
  return rel === "main.js" || rel.startsWith("lib" + path.sep);
});
// --- Gotcha 1: for...of syntax ---------------------------------------------
const FOR_OF_PATTERN = /\bfor\s*\(\s*(?:const|let|var)\s+\w+\s+of\s+/;
const forOfHits = [];
for (const file of jsFiles) {
  const text = fs.readFileSync(file, "utf8");
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (FOR_OF_PATTERN.test(lines[i])) {
      forOfHits.push(path.relative(repo, file) + ":" + (i + 1));
    }
  }
}
ok(
  forOfHits.length === 0,
  forOfHits.length === 0
    ? "no for...of loops in compiled output (Rhino interpreted mode can't run them)"
    : "no for...of loops in compiled output — found in: " + forOfHits.join(", "),
);
// --- Gotcha 2: duplicate top-level require() local binding names ----------
// Matches both `import x = require("...")` and `const x: T = require("...")`
// (main.js's style, forced by the exports-stamp fix — see gotcha #3 above).
const REQUIRE_BINDING_PATTERN = /^(?:const|var|let)\s+(\w+)\s*=\s*require\(/;
const bindingsByName = new Map();
for (const file of productionFiles) {
  const text = fs.readFileSync(file, "utf8");
  const lines = text.split("\n");
  for (const line of lines) {
    const m = line.match(REQUIRE_BINDING_PATTERN);
    if (!m) continue;
    const name = m[1];
    const list = bindingsByName.get(name) || [];
    list.push(path.relative(repo, file));
    bindingsByName.set(name, list);
  }
}
const duplicates = [];
bindingsByName.forEach((files, name) => {
  const uniqueFiles = Array.from(new Set(files));
  if (uniqueFiles.length > 1) {
    duplicates.push(name + " (" + uniqueFiles.join(", ") + ")");
  }
});
ok(
  duplicates.length === 0,
  duplicates.length === 0
    ? "every require() local binding name is unique across the whole codebase"
    : "require() binding names must be globally unique — collisions: " + duplicates.join("; "),
);
console.log("1.." + n);
process.exit(failed === 0 ? 0 : 1);
