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
    // Not JSON — a short plain-text body is shown as-is, but markup (a proxy's
    // HTML error page) never is.
    const text = body.trim();
    return text && !text.startsWith("<") ? text.slice(0, MAX_BODY_CHARS) : generic;
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

const UNREACHABLE = "Can't reach the server. Check that the backend is running, then try again.";
// What fetch() throws when nothing answered at all, by browser.
const NETWORK_FAILURE = /failed to fetch|networkerror|load failed|network request failed/i;

function endSentence(text: string): string {
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

/**
 * One readable sentence for why a request failed, for banners and notices:
 * - an error that carries an HTTP status (the app's ApiError) gives the server's
 *   own readable detail;
 * - fetch() rejecting (a TypeError such as "Failed to fetch") means nothing
 *   answered, so the server is unreachable;
 * - anything else is not something a reader can act on, so it says so plainly
 *   rather than showing a raw exception message.
 * Duck-typed on `status` so this file stays import-free.
 */
export function failureReason(err: unknown): string {
  if (err instanceof Error) {
    if (typeof (err as { status?: unknown }).status === "number" && err.message.trim()) {
      return endSentence(err.message.trim());
    }
    if (err instanceof TypeError && NETWORK_FAILURE.test(err.message)) return UNREACHABLE;
  }
  return "Something went wrong.";
}
