#!/usr/bin/env node
// i18n coverage + hard-coded string check.
// Extracts user-facing English literals from app/ and src/components (JSX text and UI props),
// then checks each has a Hindi entry in src/i18n-hi.ts. Exit 1 if any are missing.
// Usage: node scripts/i18n-check.js [--list]
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const DIRS = ["app", "src/components"];
const PROPS = ["title", "subtitle", "label", "placeholder", "message", "hint", "error"];
const files = [];
const walk = (d) =>
  fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (p.endsWith(".tsx")) files.push(p);
  });
DIRS.forEach((d) => walk(path.join(ROOT, d)));

// Brand names, sample/placeholder data and code-ish values are intentionally not translated.
const IGNORE = new Set(["SchoolPulse OS", "EVS", "SV2001", "you@school.in", "Class 7", "2026-27", "2026-04-01", "2027-03-31", "C", "7", "2016-08-14", "Plot 12"]);
const found = new Map();
const add = (s, f) => {
  s = s.replace(/\s+/g, " ").trim();
  if (IGNORE.has(s) || /^[:?]/.test(s)) return;
  if (!/[A-Za-z]{2}/.test(s) || /^[a-z0-9_.\-/]+$/.test(s) || s.startsWith("#")) return;
  if (!found.has(s)) found.set(s, new Set());
  found.get(s).add(path.relative(ROOT, f));
};
for (const f of files) {
  const src = fs.readFileSync(f, "utf8").replace(/\/\/.*$/gm, "");
  // JSX text between tags: >Some text<
  for (const m of src.matchAll(/>([^<>{}]*[A-Za-z][^<>{}]*)</g)) {
    const t = m[1].trim();
    if (t && !/[=;()]/.test(t)) add(t, f);
  }
  // UI props: title="..." label="..."
  for (const m of src.matchAll(new RegExp(`\\b(?:${PROPS.join("|")})=\\"([^\\"]+)\\"`, "g"))) add(m[1], f);
  // toast.show("...") and throw new Error("...")
  for (const m of src.matchAll(/(?:toast\.show|new Error)\(\s*"([^"]+)"/g)) add(m[1], f);
  // option labels: label: "..."
  for (const m of src.matchAll(/\b(?:label|sub|title): "([^"]+)"/g)) add(m[1], f);
}

const hiSrc = fs.readFileSync(path.join(ROOT, "src/i18n-hi.ts"), "utf8");
const keys = new Set([...hiSrc.matchAll(/^\s*"((?:[^"\\]|\\.)+)":/gm)].map((m) => m[1].replace(/\\"/g, '"')));
// Dynamic template strings in UI props are measured separately (not catalogue-checked).
let dynamic = 0;
for (const f of files) dynamic += (fs.readFileSync(f, "utf8").match(/(?:title|subtitle|label|message)=\{`[^`]*[A-Za-z]{3}/g) || []).length;
const missing = [...found.keys()].filter((k) => !keys.has(k)).sort();
const total = found.size;
const pct = total ? (((total - missing.length) / total) * 100).toFixed(1) : "100";
if (process.argv.includes("--list")) missing.forEach((m) => console.log(JSON.stringify(m), "<-", [...found.get(m)].join(",")));
console.log(`i18n: dynamic template UI props (English-only interpolations): ${dynamic}`);
console.log(`i18n: ${total - missing.length}/${total} static UI strings have Hindi (${pct}%). Missing: ${missing.length}`);
process.exit(missing.length ? 1 : 0);
