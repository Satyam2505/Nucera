// Reads a newline-delimited stream (one JSON value per line) as it arrives.
// Free of imports and DOM types beyond the Web Streams API, so it is testable
// under plain Node.

/**
 * Reads `body` to the end, calling `onItem` for every line `parse` accepts.
 * Lines can be split across network chunks (and a multi-byte character across
 * two), so bytes are decoded as a stream and only whole lines are parsed.
 * `parse` returns null for a line to skip. If `onItem` throws, the stream is
 * cancelled (which closes the connection) before the error propagates.
 */
export async function readNdjson<T>(
  body: ReadableStream<Uint8Array>,
  parse: (line: string) => T | null,
  onItem: (item: T) => void
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const flushLine = (raw: string) => {
    const line = raw.trim();
    if (!line) return;
    const item = parse(line);
    if (item !== null) onItem(item);
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        flushLine(line);
        newline = buffer.indexOf("\n");
      }
    }
    buffer += decoder.decode();
    flushLine(buffer);
    finished = true;
  } finally {
    if (!finished) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
