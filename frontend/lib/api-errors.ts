// Pure helpers for turning API failures into something worth showing. Kept
// free of imports (no token storage, no fetch) so they are testable on their
// own under plain Node, like the graph modules.

const MAX_BODY_CHARS = 200;

/**
 * The human-readable part of an error response. FastAPI sends
 * {"detail": "text"} for errors we raise and {"detail": [{loc, msg}, ...]}
 * for request validation; anything else falls back to the raw body, then to
 * a generic line, so a banner never shows a JSON blob.
 */
export function errorDetail(status: number, body: string): string {
  const generic = `Request failed (${status})`;
  try {
    const parsed: unknown = JSON.parse(body);
    const detail = (parsed as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => {
          const msg = typeof item?.msg === "string" ? item.msg : "";
          const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : undefined;
          return msg && typeof field === "string" ? `${field}: ${msg}` : msg;
        })
        .filter(Boolean);
      if (parts.length) return parts.join("; ");
    }
    // Valid JSON, but nothing readable in it: never show the blob.
    return generic;
  } catch {
    // Not JSON — a plain-text body (a proxy error page, say) is shown as-is.
    const text = body.trim();
    return text ? text.slice(0, MAX_BODY_CHARS) : generic;
  }
}

/**
 * Whether a failed response means "the session you were using is no longer
 * valid". Only a 401 to a request that actually carried a token counts: a 401
 * from the login call (wrong password) or from a request sent while logged
 * out is just an error to show, and must not trigger a sign-out.
 */
export function isSessionExpiry(status: number, sentToken: boolean): boolean {
  return status === 401 && sentToken;
}
