// Reads the real theme CSS (app/globals.css) and answers one question: is each text
// token readable (WCAG AA, 4.5:1) on every background it is used on, in the light
// theme, the dark theme, and the OS-dark fallback that applies when no data-theme
// attribute is set? Pure and import-free so it runs under plain Node (see
// theme-contrast.test.ts); it never guesses: a value it cannot read, a variable that
// does not exist, or a circular reference is an error, not a pass.

export class ThemeCssError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ThemeCssError";
  }
}

export interface Color {
  r: number;
  g: number;
  b: number;
  a: number;
}

export type VarMap = Map<string, string>;
export type ThemeName = "light" | "dark" | "dark-fallback";

export interface ThemeCss {
  light: VarMap;
  dark: VarMap;
  darkFallback: VarMap;
}

// --- reading the CSS ---------------------------------------------------------------------------

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

// The first of `targets` outside quotes and parentheses (so the ";" inside
// url("...;...") and the "{" inside selectors like :not([data-theme="light"]) are skipped).
function findTopLevel(src: string, from: number, targets: string): number {
  let depth = 0;
  let quote = "";
  for (let i = from; i < src.length; i++) {
    const ch = src[i];
    if (quote) {
      if (ch === "\\") i++;
      else if (ch === quote) quote = "";
      continue;
    }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "(") depth++;
    else if (ch === ")") depth = Math.max(0, depth - 1);
    else if (depth === 0 && targets.includes(ch)) return i;
  }
  return -1;
}

function matchingBrace(src: string, open: number): number {
  let depth = 0;
  let quote = "";
  for (let i = open; i < src.length; i++) {
    const ch = src[i];
    if (quote) {
      if (ch === "\\") i++;
      else if (ch === quote) quote = "";
      continue;
    }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "{") depth++;
    else if (ch === "}" && --depth === 0) return i;
  }
  throw new ThemeCssError("Unbalanced braces in the theme CSS");
}

interface Rule {
  selector: string;
  body: string;
}

function scanRules(src: string): Rule[] {
  const rules: Rule[] = [];
  let i = 0;
  for (;;) {
    while (i < src.length && /\s/.test(src[i])) i++;
    if (i >= src.length) return rules;
    const stop = findTopLevel(src, i, "{;");
    if (stop === -1) throw new ThemeCssError(`Unterminated rule near "${src.slice(i, i + 60)}"`);
    if (src[stop] === ";") {
      i = stop + 1; // an @import statement
      continue;
    }
    const close = matchingBrace(src, stop);
    rules.push({ selector: src.slice(i, stop).replace(/\s+/g, " ").trim(), body: src.slice(stop + 1, close) });
    i = close + 1;
  }
}

function customProperties(body: string): VarMap {
  const vars: VarMap = new Map();
  let i = 0;
  while (i < body.length) {
    const end = findTopLevel(body, i, ";");
    const chunk = body.slice(i, end === -1 ? body.length : end);
    i = end === -1 ? body.length : end + 1;
    const colon = chunk.indexOf(":");
    if (colon === -1) continue;
    const name = chunk.slice(0, colon).trim();
    if (name.startsWith("--")) vars.set(name, chunk.slice(colon + 1).trim().replace(/\s+/g, " "));
  }
  return vars;
}

const DARK_SELECTOR = ':root[data-theme="dark"]';
const FALLBACK_MEDIA = "@media (prefers-color-scheme: dark)";
const FALLBACK_SELECTOR = ':root:not([data-theme="light"])';

/** The custom properties declared for each theme scope. Throws if a scope is missing. */
export function parseThemeCss(css: string): ThemeCss {
  const rules = scanRules(stripComments(css));

  const lightRules = rules.filter((r) => r.selector === ":root");
  if (lightRules.length === 0) throw new ThemeCssError("No :root rule found (the light theme)");
  const light: VarMap = new Map();
  for (const rule of lightRules) for (const [k, v] of customProperties(rule.body)) light.set(k, v);

  const darkRules = rules.filter((r) => r.selector === DARK_SELECTOR);
  if (darkRules.length !== 1) throw new ThemeCssError(`Expected one ${DARK_SELECTOR} rule, found ${darkRules.length}`);

  const mediaRules = rules.filter((r) => r.selector === FALLBACK_MEDIA);
  if (mediaRules.length !== 1) throw new ThemeCssError(`Expected one ${FALLBACK_MEDIA} rule, found ${mediaRules.length}`);
  const inner = scanRules(mediaRules[0].body).filter((r) => r.selector === FALLBACK_SELECTOR);
  if (inner.length !== 1) {
    throw new ThemeCssError(`Expected one ${FALLBACK_SELECTOR} rule inside ${FALLBACK_MEDIA}, found ${inner.length}`);
  }

  return { light, dark: customProperties(darkRules[0].body), darkFallback: customProperties(inner[0].body) };
}

/** What an element sees in a theme: the light declarations, overridden by the theme's own. */
export function themeVariables(theme: ThemeCss, name: ThemeName): VarMap {
  const merged: VarMap = new Map(theme.light);
  if (name === "light") return merged;
  for (const [k, v] of name === "dark" ? theme.dark : theme.darkFallback) merged.set(k, v);
  return merged;
}

/** Variables the fallback block and the dark block declare differently (or only one of). */
export function fallbackDrift(theme: ThemeCss): string[] {
  const problems: string[] = [];
  for (const [name, value] of theme.dark) {
    if (!theme.darkFallback.has(name)) problems.push(`${name} is missing from the fallback block`);
    else if (theme.darkFallback.get(name) !== value) {
      problems.push(`${name}: dark block has "${value}" but the fallback has "${theme.darkFallback.get(name)}"`);
    }
  }
  for (const name of theme.darkFallback.keys()) {
    if (!theme.dark.has(name)) problems.push(`${name} is only in the fallback block`);
  }
  return problems;
}

// --- resolving variables -------------------------------------------------------------------------

const VAR_REFERENCE = /var\(\s*(--[\w-]+)\s*(?:,([^()]*))?\)/;

export function resolveVariable(vars: VarMap, name: string, stack: string[] = []): string {
  if (stack.includes(name)) throw new ThemeCssError(`Circular variable reference: ${[...stack, name].join(" -> ")}`);
  const raw = vars.get(name);
  if (raw === undefined) {
    const by = stack.length ? ` (needed by ${stack[stack.length - 1]})` : "";
    throw new ThemeCssError(`Missing variable ${name}${by}`);
  }
  let out = raw;
  for (let guard = 0; guard < 50; guard++) {
    const match = VAR_REFERENCE.exec(out);
    if (!match) return out;
    const [whole, ref, fallback] = match;
    let replacement: string;
    if (vars.has(ref)) replacement = resolveVariable(vars, ref, [...stack, name]);
    else if (fallback !== undefined) replacement = fallback.trim();
    else throw new ThemeCssError(`Missing variable ${ref} (needed by ${name})`);
    out = out.slice(0, match.index) + replacement + out.slice(match.index + whole.length);
  }
  throw new ThemeCssError(`var() nested too deeply in ${name}`);
}

// --- colours --------------------------------------------------------------------------------------

const SUPPORTED = "#rgb, #rgba, #rrggbb, #rrggbbaa, or rgb()/rgba() with comma-separated numbers";

export function parseColor(value: string): Color {
  const v = value.trim().toLowerCase();

  const hex = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/.exec(v);
  if (hex && [3, 4, 6, 8].includes(hex[1].length)) {
    let digits = hex[1];
    if (digits.length <= 4) digits = digits.split("").map((d) => d + d).join("");
    const byte = (i: number) => parseInt(digits.slice(i, i + 2), 16);
    return { r: byte(0), g: byte(2), b: byte(4), a: digits.length === 8 ? byte(6) / 255 : 1 };
  }

  const fn = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)(%?)\s*)?\)$/.exec(v);
  if (fn) {
    const [r, g, b] = [Number(fn[1]), Number(fn[2]), Number(fn[3])];
    const a = fn[4] === undefined ? 1 : Number(fn[4]) / (fn[5] ? 100 : 1);
    if ([r, g, b].some((n) => !(n >= 0 && n <= 255)) || !(a >= 0 && a <= 1)) {
      throw new ThemeCssError(`Colour out of range: "${value}"`);
    }
    return { r, g, b, a };
  }

  throw new ThemeCssError(`Unsupported colour value "${value}" (supported: ${SUPPORTED})`);
}

export function colorOf(vars: VarMap, name: string): Color {
  try {
    return parseColor(resolveVariable(vars, name));
  } catch (err) {
    if (err instanceof ThemeCssError) throw new ThemeCssError(`${name}: ${err.message}`);
    throw err;
  }
}

/** `fg` painted over an opaque `bg`, rounded to 8-bit channels like a browser does. */
export function composite(fg: Color, bg: Color): Color {
  if (bg.a !== 1) throw new ThemeCssError("A background must be opaque; composite it over a base colour first");
  const mix = (f: number, b: number) => Math.round(f * fg.a + b * (1 - fg.a));
  return { r: mix(fg.r, bg.r), g: mix(fg.g, bg.g), b: mix(fg.b, bg.b), a: 1 };
}

function relativeLuminance(c: Color): number {
  const channel = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
}

/** WCAG 2 contrast ratio. Both colours must be opaque (composite translucent ones first). */
export function contrastRatio(a: Color, b: Color): number {
  if (a.a !== 1 || b.a !== 1) throw new ThemeCssError("Contrast needs opaque colours; composite translucent ones first");
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// --- what has to be readable on what ------------------------------------------------------------------

export const AA_NORMAL_TEXT = 4.5;

function withAlpha(c: Color, a: number): Color {
  return { ...c, a };
}

/** Every named background the text tokens sit on, as an opaque colour in this theme. */
export function buildSurfaces(vars: VarMap, theme: ThemeName): Record<string, Color> {
  const page = colorOf(vars, "--bg-page");
  const surface = colorOf(vars, "--bg-surface");
  const rail = colorOf(vars, "--bg-sidebar");
  const ink = parseColor(`rgb(${resolveVariable(vars, "--ink-rgb")})`);
  const accent = parseColor(`rgb(${resolveVariable(vars, "--accent-rgb")})`);
  const surfaces: Record<string, Color> = {
    page,
    surface,
    linen: colorOf(vars, "--bg-linen"),
    muted: colorOf(vars, "--muted"),
    "hover-on-page": composite(withAlpha(ink, 0.08), page),
    "hover-on-surface": composite(withAlpha(ink, 0.08), surface),
    rail,
    "rail-hover": composite(colorOf(vars, "--sidebar-accent"), rail),
    "rail-active": composite(withAlpha(accent, 0.18), rail),
    // Destructive buttons and badges: the destructive colour as text on a tint of itself
    // (bg-destructive/10 in light, /20 in dark; see components/ui/button.tsx).
    "destructive-tint": composite(withAlpha(colorOf(vars, "--destructive"), theme === "light" ? 0.1 : 0.2), surface),
  };
  for (const [prefix, bg] of [
    ["error-bg", "--error-bg"],
    ["warn-bg", "--warn-bg"],
    ["mastered-fill", "--status-mastered-fill"],
    ["in-progress-fill", "--status-in-progress-fill"],
    ["unmastered-fill", "--status-unmastered-fill"],
    ["missed-fill", "--status-missed-fill"],
  ] as const) {
    const tint = colorOf(vars, bg); // a fill may be translucent (light) or solid (dark)
    surfaces[`${prefix}-on-page`] = composite(tint, page);
    surfaces[`${prefix}-on-surface`] = composite(tint, surface);
  }
  return surfaces;
}

export interface TextRequirement {
  text: string; // the CSS variable holding the text colour
  on: string[]; // surface names from buildSurfaces
  min: number;
}

const BODY = ["page", "surface", "linen", "muted", "hover-on-page", "hover-on-surface"];
const RAIL = ["rail", "rail-hover", "rail-active"];
const fills = (status: string) => [`${status}-fill-on-page`, `${status}-fill-on-surface`];

export const REQUIREMENTS: TextRequirement[] = [
  { text: "--ink", on: BODY, min: AA_NORMAL_TEXT },
  { text: "--text-secondary", on: BODY, min: AA_NORMAL_TEXT },
  { text: "--text-tertiary", on: BODY, min: AA_NORMAL_TEXT },
  { text: "--muted-foreground", on: BODY, min: AA_NORMAL_TEXT },
  { text: "--text-placeholder", on: ["page", "surface", "linen"], min: AA_NORMAL_TEXT },
  { text: "--sidebar-foreground", on: RAIL, min: AA_NORMAL_TEXT },
  { text: "--sidebar-text-secondary", on: RAIL, min: AA_NORMAL_TEXT },
  { text: "--sidebar-text-tertiary", on: RAIL, min: AA_NORMAL_TEXT },
  { text: "--status-mastered-text", on: [...BODY, ...fills("mastered")], min: AA_NORMAL_TEXT },
  { text: "--status-in-progress-text", on: [...BODY, ...fills("in-progress")], min: AA_NORMAL_TEXT },
  { text: "--status-unmastered-text", on: [...BODY, ...fills("unmastered")], min: AA_NORMAL_TEXT },
  { text: "--status-missed-text", on: [...BODY, ...fills("missed")], min: AA_NORMAL_TEXT },
  { text: "--error-text", on: ["page", "surface", "linen", "error-bg-on-page", "error-bg-on-surface"], min: AA_NORMAL_TEXT },
  { text: "--warn-text", on: ["page", "surface", "linen", "warn-bg-on-page", "warn-bg-on-surface"], min: AA_NORMAL_TEXT },
  { text: "--destructive", on: ["destructive-tint"], min: AA_NORMAL_TEXT },
];

export interface Measurement {
  text: string;
  surface: string;
  ratio: number;
  min: number;
}

/** Every text/surface pair in a theme with its measured ratio. Throws on anything unreadable. */
export function measureTheme(
  vars: VarMap,
  theme: ThemeName,
  requirements: TextRequirement[] = REQUIREMENTS
): Measurement[] {
  const surfaces = buildSurfaces(vars, theme);
  const out: Measurement[] = [];
  for (const req of requirements) {
    const text = colorOf(vars, req.text);
    for (const name of req.on) {
      const bg = surfaces[name];
      if (!bg) throw new ThemeCssError(`Unknown surface "${name}" required for ${req.text}`);
      out.push({ text: req.text, surface: name, ratio: contrastRatio(text, bg), min: req.min });
    }
  }
  return out;
}

export function failures(measurements: Measurement[]): Measurement[] {
  return measurements.filter((m) => m.ratio < m.min);
}

export function describeFailures(list: Measurement[]): string {
  return list.map((m) => `${m.text} on ${m.surface}: ${m.ratio.toFixed(2)}:1 (needs ${m.min}:1)`).join("\n");
}
