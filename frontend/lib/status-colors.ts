export type MasteryStatusKey = "mastered" | "in_progress" | "unmastered" | "missed";

// Validated against the app's cream surface (#ECE7D1) with the dataviz
// skill's validator: lightness band, chroma floor, CVD separation, and
// normal-vision floor all pass for the three true status hues. Amber
// under-clears 3:1 contrast (a WARN, not a FAIL) — legal because every use
// pairs the color with a text label, never color alone. "unmastered"
// deliberately sits outside the ramp (not a status, just "no signal yet")
// and uses a neutral warm gray instead.
export const STATUS_COLOR: Record<MasteryStatusKey, string> = {
  mastered: "#3f7d3a",
  in_progress: "#c9860f",
  unmastered: "#857f6b",
  missed: "#b23a2f",
};

// Translucent tints of the same hues, for fills on the cream surface
// (node backgrounds, badge backgrounds, donut track segments).
export const STATUS_FILL: Record<MasteryStatusKey, string> = {
  mastered: "rgba(63, 125, 58, 0.14)",
  in_progress: "rgba(201, 134, 15, 0.16)",
  unmastered: "rgba(34, 34, 34, 0.07)",
  missed: "rgba(178, 58, 47, 0.14)",
};

export const STATUS_LABEL: Record<MasteryStatusKey, string> = {
  mastered: "Mastered",
  in_progress: "In progress",
  unmastered: "Unmastered",
  missed: "Missed",
};
