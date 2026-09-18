// Pure camera math for the Nucera knowledge graph. Everything here works on
// plain rectangles/numbers in screen space (pixels relative to the canvas),
// so it can be unit tested without React Flow. Nothing here reads or writes
// node positions — only how the camera should move.

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export function unionRects(rects: Rect[]): Rect {
  return {
    left: Math.min(...rects.map((r) => r.left)),
    top: Math.min(...rects.map((r) => r.top)),
    right: Math.max(...rects.map((r) => r.right)),
    bottom: Math.max(...rects.map((r) => r.bottom)),
  };
}

/** True when `target` fits inside `visible` (with `margin` on every side) at all. */
export function rectFits(target: Rect, visible: Rect, margin: number): boolean {
  return (
    target.right - target.left <= visible.right - visible.left - margin * 2 &&
    target.bottom - target.top <= visible.bottom - visible.top - margin * 2
  );
}

function axisDelta(start: number, end: number, visStart: number, visEnd: number, margin: number): number {
  if (start < visStart + margin) return visStart + margin - start;
  if (end > visEnd - margin) return Math.min(visEnd - margin - end, 0) || 0;
  return 0;
}

/**
 * Smallest camera shift that brings `target` inside `visible` (with margin).
 * Returns zero on an axis that is already fine. If the target is larger than
 * the visible area on an axis, its leading edge wins so the start of it is
 * never hidden. The camera moves; the topic never does.
 */
export function revealDelta(target: Rect, visible: Rect, margin: number): { dx: number; dy: number } {
  let dx = axisDelta(target.left, target.right, visible.left, visible.right, margin);
  let dy = axisDelta(target.top, target.bottom, visible.top, visible.bottom, margin);
  // If shifting to reveal the far edge would push the near edge out of view,
  // prefer keeping the near edge visible.
  if (target.left + dx < visible.left + margin) dx = visible.left + margin - target.left;
  if (target.top + dy < visible.top + margin) dy = visible.top + margin - target.top;
  return { dx, dy };
}

/** True when any rect overlaps `visible` — used to reject a stale saved camera. */
export function anyRectVisible(rects: Rect[], visible: Rect): boolean {
  return rects.some(
    (r) => r.right > visible.left && r.left < visible.right && r.bottom > visible.top && r.top < visible.bottom
  );
}

export function clampZoom(zoom: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, zoom));
}

/**
 * One zoom-button step: a fixed additive step (e.g. 0.15 = 15 percentage
 * points, so 100% -> 115% -> 130%), clamped to the allowed range. Values are
 * rounded so repeated steps don't accumulate float noise (1.1500000000000001).
 */
export function stepZoom(current: number, direction: 1 | -1, step: number, min: number, max: number): number {
  const next = Math.round((current + direction * step) * 1000) / 1000;
  return clampZoom(next, min, max);
}

/** Zoom as the whole-number percentage shown in the zoom control. */
export function zoomPercent(zoom: number): number {
  return Math.round(zoom * 100);
}
