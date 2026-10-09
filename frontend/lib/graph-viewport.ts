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

export interface Camera {
  x: number;
  y: number;
  zoom: number;
}

export interface FitOptions {
  /** Fraction of extra space around the graph, as React Flow's `fitView` padding. */
  padding: number;
  maxZoom: number;
}

/**
 * The camera React Flow's `fitView` would pick for `bounds` (graph coordinates) on a
 * canvas of `canvas` pixels: the whole graph, centred, at the largest zoom that fits.
 * Same formula as React Flow's getViewportForBounds, minus its lower zoom clamp.
 */
export function fitViewport(bounds: Rect, canvas: { width: number; height: number }, options: FitOptions): Camera {
  const width = Math.max(bounds.right - bounds.left, 1);
  const height = Math.max(bounds.bottom - bounds.top, 1);
  const xZoom = canvas.width / (width * (1 + options.padding));
  const yZoom = canvas.height / (height * (1 + options.padding));
  const zoom = Math.min(options.maxZoom, Math.min(xZoom, yZoom));
  return {
    x: canvas.width / 2 - ((bounds.left + bounds.right) / 2) * zoom,
    y: canvas.height / 2 - ((bounds.top + bounds.bottom) / 2) * zoom,
    zoom,
  };
}

/**
 * The default camera: the whole graph when that is at least `minReadableZoom`.
 * A wide, short graph on a narrow canvas would otherwise shrink to an unreadable
 * size, so below that floor the zoom is held at `minReadableZoom` (never above
 * `maxZoom`), the graph's left edge sits where the normal fit would leave its left
 * margin, and the graph is centred vertically. The rest is reachable by panning.
 */
export function readableFitViewport(
  bounds: Rect,
  canvas: { width: number; height: number },
  options: FitOptions & { minReadableZoom: number }
): Camera {
  const fit = fitViewport(bounds, canvas, options);
  if (fit.zoom >= options.minReadableZoom) return fit;
  const zoom = Math.min(options.minReadableZoom, options.maxZoom);
  const leftMargin = (canvas.width * options.padding) / (2 * (1 + options.padding));
  return {
    x: leftMargin - bounds.left * zoom,
    y: canvas.height / 2 - ((bounds.top + bounds.bottom) / 2) * zoom,
    zoom,
  };
}
