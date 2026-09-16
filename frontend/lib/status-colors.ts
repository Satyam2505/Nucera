export type MasteryStatusKey = "mastered" | "in_progress" | "unmastered" | "missed";

// Validated against the app's cream surface (#ECE7D1) with the dataviz
// skill's validator: lightness band, chroma floor, CVD separation, and
// normal-vision floor all pass for the three true status hues. Amber
// under-clears 3:1 contrast (a WARN, not a FAIL) — legal because every use
// pairs the color with a text label, never color alone. "unmastered"
// deliberately sits outside the ramp (not a status, just "no signal yet")
// and uses a neutral warm gray instead.
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
