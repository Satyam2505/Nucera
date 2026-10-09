export type MasteryStatusKey = "mastered" | "in_progress" | "unmastered" | "missed";

// These hues were validated with the dataviz skill's validator (lightness band,
// chroma floor, CVD separation) against an earlier cream surface (#ECE7D1); that
// validation has not been re-run on the current surfaces. Measured on today's
// light theme, amber is ~2.8–3.0:1 and unmastered ~3.7–4.0:1, so neither is
// AA-readable as text; dark-theme statuses are all ≥4.7:1. Pair status colors with
// a text label or icon where possible. Known exceptions: the module-rail dot
// (colour only) and the Mastery breakdown heading, which uses the color as text
// (tracked for Phase 2 text tokens). "unmastered" deliberately sits outside the
// ramp (not a status, just "no signal yet") and uses a neutral gray (warm in light
// mode, cool in dark).
//
// Values are CSS custom properties (see globals.css) so every consumer —
// Tailwind inline styles, React Flow node styles, raw SVG — repaints for
// dark mode automatically without any JS-side theme check.
export const STATUS_COLOR: Record<MasteryStatusKey, string> = {
  mastered: "var(--status-mastered)",
  in_progress: "var(--status-in-progress)",
  unmastered: "var(--status-unmastered)",
  missed: "var(--status-missed)",
};

// Translucent tints of the same hues, for fills on the surface
// (node backgrounds, badge backgrounds, donut track segments).
export const STATUS_FILL: Record<MasteryStatusKey, string> = {
  mastered: "var(--status-mastered-fill)",
  in_progress: "var(--status-in-progress-fill)",
  unmastered: "var(--status-unmastered-fill)",
  missed: "var(--status-missed-fill)",
};

export const STATUS_LABEL: Record<MasteryStatusKey, string> = {
  mastered: "Mastered",
  in_progress: "In progress",
  unmastered: "Unmastered",
  missed: "Missed",
};
