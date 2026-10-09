// Plain-Node tests for the theme contrast checker and for the real theme in
// app/globals.css. Run with `npm test` (or `npm test -- theme-contrast`); see
// scripts/test-lib.mjs.
//
// Three kinds of test, in this order:
//  1. calibration: the checker agrees with contrast ratios published for WCAG 2;
//  2. negative controls: it rejects what it should (a low-contrast token, a drifted
//     fallback, an unreadable value, a missing or circular variable, a missing block),
//     including by mutating the REAL css, so a regression in the checker or in the
//     css cannot pass silently;
//  3. the real theme: every text token clears 4.5:1 on every surface it is used on in
//     the light theme, the dark theme, and the retained OS-dark fallback.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { STATUS_COLOR, STATUS_FILL, STATUS_TEXT_COLOR } from "./status-colors";
import {
  AA_NORMAL_TEXT,
  composite,
  contrastRatio,
  describeFailures,
  failures,
  fallbackDrift,
  measureTheme,
  parseColor,
  parseThemeCss,
  REQUIREMENTS,
  resolveVariable,
  ThemeCssError,
  themeVariables,
  type ThemeName,
  type VarMap,
} from "./theme-contrast";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

// Line endings are normalised so the mutations below can match multi-line snippets
// whether git checked the file out with LF or CRLF.
const CSS = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const THEMES: ThemeName[] = ["light", "dark", "dark-fallback"];

function ratio(fg: string, bg: string): number {
  return contrastRatio(parseColor(fg), parseColor(bg));
}

// Replaces `from` with `to` exactly once, after `marker` (so a value that appears in both
// the dark block and the fallback can be changed in only one of them).
function mutate(css: string, from: string, to: string, marker = ""): string {
  const start = marker ? css.indexOf(marker) : 0;
  assert.ok(start !== -1, `marker not found: ${marker}`);
  const at = css.indexOf(from, start);
  assert.ok(at !== -1, `expected css to contain "${from}"${marker ? ` after "${marker}"` : ""}`);
  return css.slice(0, at) + to + css.slice(at + from.length);
}

function measure(css: string, theme: ThemeName) {
  return measureTheme(themeVariables(parseThemeCss(css), theme), theme);
}

function failedTokens(css: string, theme: ThemeName): string[] {
  return [...new Set(failures(measure(css, theme)).map((f) => f.text))].sort();
}

// --- 1. calibration -----------------------------------------------------------------------------------
test("calibration: black on white is 21:1 and a colour on itself is 1:1", () => {
  assert.equal(Math.round(ratio("#000000", "#ffffff") * 100) / 100, 21);
  assert.equal(ratio("#ffffff", "#ffffff"), 1);
  assert.equal(ratio("#336699", "#336699"), 1);
});

test("calibration: published WCAG values (#767676 is the lightest grey that passes AA on white)", () => {
  assert.equal(ratio("#767676", "#ffffff").toFixed(2), "4.54");
  assert.equal(ratio("#777777", "#ffffff").toFixed(2), "4.48");
  assert.equal(ratio("#595959", "#ffffff").toFixed(2), "7.00");
  assert.equal(ratio("#ff0000", "#ffffff").toFixed(2), "4.00");
});

test("calibration: the ratio is symmetric and shorthand hex means the same colour", () => {
  assert.equal(ratio("#123456", "#fedcba"), ratio("#fedcba", "#123456"));
  assert.deepEqual(parseColor("#abc"), parseColor("#aabbcc"));
  assert.equal(ratio("#fff", "#000"), ratio("#ffffff", "#000000"));
});

test("calibration: transparency is composited over the background before measuring", () => {
  const half = composite(parseColor("rgba(0, 0, 0, 0.5)"), parseColor("#ffffff"));
  assert.deepEqual(half, { r: 128, g: 128, b: 128, a: 1 });
  assert.deepEqual(composite(parseColor("#80808000"), parseColor("#102030")), parseColor("#102030"));
  assert.deepEqual(composite(parseColor("rgba(255, 0, 0, 1)"), parseColor("#ffffff")), parseColor("#ff0000"));
  // Text on a translucent tint reads as text on the blended colour.
  const tint = composite(parseColor("rgba(255, 0, 0, 0.1)"), parseColor("#ffffff"));
  assert.ok(ratio("#000000", "#ffffff") > contrastRatio(parseColor("#000000"), tint));
});

test("calibration: hex alpha, rgb() and rgba() forms parse to the same colours", () => {
  assert.deepEqual(parseColor("rgb(26, 31, 58)"), parseColor("#1a1f3a"));
  assert.deepEqual(parseColor("rgba(255, 255, 255, 0.08)"), { r: 255, g: 255, b: 255, a: 0.08 });
  assert.equal(parseColor("#ffffff80").a.toFixed(2), "0.50");
  assert.equal(parseColor("rgba(0,0,0,50%)").a, 0.5);
});

// --- 2. negative controls: the parser and resolver refuse what they cannot read -------------------------
test("a colour the checker cannot read is an error, never a pass", () => {
  for (const value of [
    "hsl(0 0% 50%)",
    "oklch(0.5 0.1 200)",
    "color-mix(in srgb, red 50%, white)",
    "red",
    "transparent",
    "currentColor",
    "#12",
    "#12345",
    "#ggg",
    "rgb(1 2 3)",
    "rgb(1, 2)",
    "",
  ]) {
    assert.throws(() => parseColor(value), ThemeCssError, `should reject "${value}"`);
  }
  assert.throws(() => parseColor("rgb(300, 0, 0)"), /out of range/);
  assert.throws(() => parseColor("rgba(0, 0, 0, 1.5)"), /out of range/);
});

test("an unreadable value in the real css is reported with the token it belongs to", () => {
  const bad = mutate(CSS, "--text-secondary: #3c4356;", "--text-secondary: oklch(0.4 0.02 260);");
  assert.throws(() => measure(bad, "light"), /--text-secondary: Unsupported colour value "oklch/);
});

test("variables: references resolve through aliases, fallbacks work, and a missing one is an error", () => {
  const vars: VarMap = new Map([
    ["--a", "var(--b)"],
    ["--b", "#112233"],
    ["--rgb", "26, 31, 58"],
    ["--wrapped", "rgba(var(--rgb), 0.5)"],
    ["--with-fallback", "var(--nope, #abcdef)"],
    ["--dangling", "var(--nope)"],
  ]);
  assert.equal(resolveVariable(vars, "--a"), "#112233");
  assert.equal(resolveVariable(vars, "--wrapped"), "rgba(26, 31, 58, 0.5)");
  assert.equal(resolveVariable(vars, "--with-fallback"), "#abcdef");
  assert.throws(() => resolveVariable(vars, "--dangling"), /Missing variable --nope \(needed by --dangling\)/);
  assert.throws(() => resolveVariable(vars, "--absent"), /Missing variable --absent/);
});

test("variables: circular references are an error", () => {
  const cycle: VarMap = new Map([
    ["--a", "var(--b)"],
    ["--b", "var(--a)"],
    ["--self", "var(--self)"],
  ]);
  assert.throws(() => resolveVariable(cycle, "--a"), /Circular variable reference: --a -> --b -> --a/);
  assert.throws(() => resolveVariable(cycle, "--self"), /Circular/);
});

test("removing a variable the checker needs fails loudly", () => {
  const without = mutate(CSS, "  --text-placeholder: #667085;\n", "");
  assert.throws(() => measure(without, "light"), /Missing variable --text-placeholder/);
  assert.throws(() => measureTheme(themeVariables(parseThemeCss(CSS), "light"), "light", [{ text: "--nope", on: ["page"], min: 4.5 }]), /Missing variable --nope/);
  assert.throws(
    () => measureTheme(themeVariables(parseThemeCss(CSS), "light"), "light", [{ text: "--ink", on: ["no-such-surface"], min: 4.5 }]),
    /Unknown surface "no-such-surface"/
  );
});

test("translucent colours cannot be measured without being composited first", () => {
  assert.throws(() => contrastRatio(parseColor("rgba(0,0,0,0.5)"), parseColor("#fff")), /opaque/);
  assert.throws(() => composite(parseColor("#000"), parseColor("rgba(255,255,255,0.5)")), /opaque/);
});

test("the css scopes must all exist: a missing or renamed block is an error", () => {
  assert.throws(() => parseThemeCss(""), /No :root rule/);
  assert.throws(() => parseThemeCss(mutate(CSS, '@media (prefers-color-scheme: dark)', "@media (prefers-reduced-motion: reduce)")), /Expected one @media \(prefers-color-scheme: dark\) rule, found 0/);
  assert.throws(() => parseThemeCss(mutate(CSS, ':root:not([data-theme="light"])', ":root.fallback")), /inside @media/);
  assert.throws(() => parseThemeCss(mutate(CSS, ':root[data-theme="dark"] {', ':root[data-theme="night"] {')), /Expected one :root\[data-theme="dark"\] rule, found 0/);
  assert.throws(() => parseThemeCss(CSS + CSS.slice(CSS.indexOf(':root[data-theme="dark"] {'), CSS.indexOf('@media (prefers-color-scheme: dark)'))), /found 2/);
});

test("the reader copes with comments, quoted semicolons and nested rules", () => {
  const css = `
    /* a comment with { braces } and ; semicolons */
    @import url("https://example.com/a;b?x=1");
    :root { --a: #111111; /* trailing */ --b: var(--a) }
    :root[data-theme="dark"] { --a: #eeeeee; }
    @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --a: #eeeeee; } }
    .other { --a: #ff0000; }
  `;
  const theme = parseThemeCss(css);
  assert.equal(theme.light.get("--a"), "#111111");
  assert.equal(theme.light.get("--b"), "var(--a)");
  assert.equal(resolveVariable(themeVariables(theme, "dark"), "--b"), "#eeeeee");
  assert.deepEqual(fallbackDrift(theme), []);
});

// --- 2b. negative controls on the real css: the checker catches regressions ---------------------------
test("control: a low-contrast text token in the light theme is caught, along with the token that aliases it", () => {
  const bad = mutate(CSS, "--text-tertiary: #586075;", "--text-tertiary: #aaaaaa;");
  assert.deepEqual(failedTokens(bad, "light"), ["--muted-foreground", "--text-tertiary"]);
  assert.deepEqual(failedTokens(bad, "dark"), []); // the dark theme is a separate declaration
});

test("control: the old light muted colour (#857f6b) would have failed", () => {
  const old = mutate(CSS, "--muted-foreground: var(--text-tertiary);", "--muted-foreground: var(--status-unmastered);");
  assert.deepEqual(failedTokens(old, "light"), ["--muted-foreground"]);
});

test("control: the old dark error text (#ef4444) fails on its own background, which is why it was raised", () => {
  let old = mutate(CSS, "--error-text: #f87171;", "--error-text: #ef4444;", ':root[data-theme="dark"]');
  old = mutate(old, "--error-text: #f87171;", "--error-text: #ef4444;", "@media (prefers-color-scheme: dark)");
  const failed = failures(measure(old, "dark"));
  assert.ok(failed.some((f) => f.text === "--error-text" && f.surface === "error-bg-on-page" && f.ratio < 4.5));
  assert.ok(failures(measure(old, "dark-fallback")).some((f) => f.text === "--error-text"));
  assert.deepEqual(failedTokens(old, "light"), []);
});

test("control: a dark-only regression is caught in the dark theme and not in the light one", () => {
  const bad = mutate(CSS, "--text-secondary: #d1d5db;", "--text-secondary: #555555;", ':root[data-theme="dark"]');
  assert.deepEqual(failedTokens(bad, "dark"), ["--text-secondary"]);
  assert.deepEqual(failedTokens(bad, "light"), []);
});

test("control: a regression only in the OS-dark fallback is caught, as contrast and as drift", () => {
  const bad = mutate(CSS, "--text-secondary: #d1d5db;", "--text-secondary: #444444;", "@media (prefers-color-scheme: dark)");
  assert.deepEqual(failedTokens(bad, "dark"), []);
  assert.deepEqual(failedTokens(bad, "dark-fallback"), ["--text-secondary"]);
  const drift = fallbackDrift(parseThemeCss(bad));
  assert.equal(drift.length, 1);
  assert.match(drift[0], /--text-secondary: dark block has "#d1d5db" but the fallback has "#444444"/);
});

test("control: a token added to the dark block but forgotten in the fallback is reported", () => {
  const forgot = mutate(CSS, "    --text-placeholder: #8b93a1;\n", "", "@media (prefers-color-scheme: dark)");
  assert.deepEqual(fallbackDrift(parseThemeCss(forgot)), ["--text-placeholder is missing from the fallback block"]);
  const extra = mutate(CSS, "    --text-placeholder: #8b93a1;\n", "    --text-placeholder: #8b93a1;\n    --only-here: #000000;\n", "@media (prefers-color-scheme: dark)");
  assert.deepEqual(fallbackDrift(parseThemeCss(extra)), ["--only-here is only in the fallback block"]);
});

test("control: failures are described with the token, the surface and the ratio", () => {
  const bad = mutate(CSS, "--text-placeholder: #667085;", "--text-placeholder: #bbbbbb;");
  const text = describeFailures(failures(measure(bad, "light")));
  assert.match(text, /--text-placeholder on linen: \d\.\d\d:1 \(needs 4\.5:1\)/);
});

// --- 3. the real theme -----------------------------------------------------------------------------------
test("the real css has all three scopes and the fallback mirrors the dark block exactly", () => {
  const theme = parseThemeCss(CSS);
  assert.ok(theme.light.size > 40, `only ${theme.light.size} light variables found`);
  assert.ok(theme.dark.size > 20, `only ${theme.dark.size} dark variables found`);
  assert.deepEqual(fallbackDrift(theme), []);
  assert.equal(theme.darkFallback.size, theme.dark.size);
});

test("every requirement covers a meaningful number of surfaces (the table cannot be silently emptied)", () => {
  assert.ok(REQUIREMENTS.length >= 14);
  for (const req of REQUIREMENTS) assert.ok(req.on.length >= 1, `${req.text} is checked on no surface`);
  const expected = REQUIREMENTS.reduce((sum, req) => sum + req.on.length, 0);
  assert.ok(expected >= 70, `the requirement table shrank to ${expected} pairs`);
  for (const theme of THEMES) assert.equal(measure(CSS, theme).length, expected, `${theme}: every pair must be measured`);
});

for (const theme of THEMES) {
  test(`every text token is at least ${AA_NORMAL_TEXT}:1 on every surface it is used on (${theme})`, () => {
    const bad = failures(measure(CSS, theme));
    assert.deepEqual(bad, [], `\n${describeFailures(bad)}`);
  });
}

test("every light token exists in the dark themes; dark themes add no tokens of their own", () => {
  const theme = parseThemeCss(CSS);
  const light = themeVariables(theme, "light");
  const dark = themeVariables(theme, "dark");
  const names = (m: VarMap) => [...m.keys()].sort();
  assert.deepEqual(names(themeVariables(theme, "dark")), names(themeVariables(theme, "dark-fallback")));
  assert.deepEqual(names(light).filter((n) => !dark.has(n)), []);
  assert.deepEqual(
    names(dark).filter((n) => !light.has(n)),
    []
  );
});

test("--muted-foreground follows the tertiary text token in every theme", () => {
  const theme = parseThemeCss(CSS);
  assert.equal(theme.light.get("--muted-foreground"), "var(--text-tertiary)");
  for (const name of THEMES) {
    const vars = themeVariables(theme, name);
    assert.equal(resolveVariable(vars, "--muted-foreground"), resolveVariable(vars, "--text-tertiary"));
  }
});

test("the status text tokens are theme-aware and in-progress/missed follow the warn/error text", () => {
  const theme = parseThemeCss(CSS);
  for (const name of THEMES) {
    const vars = themeVariables(theme, name);
    assert.equal(resolveVariable(vars, "--status-in-progress-text"), resolveVariable(vars, "--warn-text"));
    assert.equal(resolveVariable(vars, "--status-missed-text"), resolveVariable(vars, "--error-text"));
  }
  const light = themeVariables(theme, "light");
  const dark = themeVariables(theme, "dark");
  assert.notEqual(resolveVariable(light, "--status-mastered-text"), resolveVariable(dark, "--status-mastered-text"));
  assert.notEqual(resolveVariable(light, "--status-unmastered-text"), resolveVariable(dark, "--status-unmastered-text"));
});

test("the Tailwind utilities map to the right tokens, and those tokens exist", () => {
  const theme = parseThemeCss(CSS);
  const mappings: Record<string, string> = {
    "--color-fg-secondary": "--text-secondary",
    "--color-fg-tertiary": "--text-tertiary",
    "--color-fg-placeholder": "--text-placeholder",
    "--color-sidebar-fg-secondary": "--sidebar-text-secondary",
    "--color-sidebar-fg-tertiary": "--sidebar-text-tertiary",
    "--color-sidebar-error": "--sidebar-error-text",
  };
  for (const [utility, token] of Object.entries(mappings)) {
    assert.match(CSS, new RegExp(`${utility}:\\s*var\\(${token}\\)\\s*;`), `${utility} is not mapped to ${token}`);
    assert.ok(theme.light.has(token), `${token} is not defined`);
  }
});

// --- status-colors.ts -----------------------------------------------------------------------------------
test("STATUS_TEXT_COLOR points at tokens that exist and are covered by the contrast requirements", () => {
  const covered = new Set(REQUIREMENTS.map((r) => r.text));
  const light = themeVariables(parseThemeCss(CSS), "light");
  const keys = Object.keys(STATUS_COLOR).sort();
  assert.deepEqual(Object.keys(STATUS_TEXT_COLOR).sort(), keys);
  for (const key of keys) {
    const token = /^var\((--[\w-]+)\)$/.exec(STATUS_TEXT_COLOR[key as keyof typeof STATUS_TEXT_COLOR])?.[1];
    assert.ok(token, `${key}: not a plain var() reference`);
    assert.ok(light.has(token), `${token} is not defined in the css`);
    assert.ok(covered.has(token), `${token} is not covered by the contrast requirements`);
  }
});

test("the existing status colours and fills are unchanged (dots, borders and graph styling use them)", () => {
  assert.deepEqual(STATUS_COLOR, {
    mastered: "var(--status-mastered)",
    in_progress: "var(--status-in-progress)",
    unmastered: "var(--status-unmastered)",
    missed: "var(--status-missed)",
  });
  assert.deepEqual(STATUS_FILL, {
    mastered: "var(--status-mastered-fill)",
    in_progress: "var(--status-in-progress-fill)",
    unmastered: "var(--status-unmastered-fill)",
    missed: "var(--status-missed-fill)",
  });
  const light = themeVariables(parseThemeCss(CSS), "light");
  assert.equal(light.get("--status-in-progress"), "#c9860f");
  assert.equal(light.get("--status-unmastered"), "#857f6b");
});

console.log(`\n${passed} passed`);
