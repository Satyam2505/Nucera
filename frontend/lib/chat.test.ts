// Plain-Node tests for the chat helpers (ndjson reader, stream events, saved
// message mapping, maths delimiters), in the same style as quiz.test.ts (only
// Node's built-in `assert`). To run ad hoc, Node's ESM loader needs the
// explicit extension on the relative imports:
//   sed 's#"./\(ndjson\|chat\)"#"./\1.ts"#' lib/chat.test.ts > lib/_run.test.ts \
//     && node --experimental-strip-types lib/_run.test.ts; rm lib/_run.test.ts

import assert from "node:assert/strict";

import { fromSaved, normalizeMath, parseStreamEvent } from "./chat";
import { readNdjson } from "./ndjson";

let passed = 0;
async function test(name: string, fn: () => void | Promise<void>) {
  await fn();
  passed++;
  console.log(`ok - ${name}`);
}

// A stream that delivers `chunks` (strings or raw bytes) one read at a time.
function streamOf(chunks: (string | Uint8Array)[], failAfter?: Error): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        const chunk = chunks[i++];
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      } else if (failAfter) {
        controller.error(failAfter);
      } else {
        controller.close();
      }
    },
    cancel() {
      cancelled = true;
    },
  });
  (stream as unknown as { wasCancelled: () => boolean }).wasCancelled = () => cancelled;
  return stream;
}

async function collect(body: ReadableStream<Uint8Array>): Promise<string[]> {
  const lines: string[] = [];
  await readNdjson(body, (line) => line, (line) => lines.push(line));
  return lines;
}

// --- readNdjson --------------------------------------------------------------------------

await test("whole lines arrive as they are read", async () => {
  assert.deepEqual(await collect(streamOf(['{"a":1}\n', '{"a":2}\n'])), ['{"a":1}', '{"a":2}']);
});

await test("a line split across network chunks is joined", async () => {
  assert.deepEqual(await collect(streamOf(['{"te', 'xt":"hi"}\n{"x"', ":2}\n"])), ['{"text":"hi"}', '{"x":2}']);
});

await test("several lines in one chunk are all delivered", async () => {
  assert.deepEqual(await collect(streamOf(["a\nb\nc\n"])), ["a", "b", "c"]);
});

await test("a final line with no newline is still delivered", async () => {
  assert.deepEqual(await collect(streamOf(["a\nb"])), ["a", "b"]);
});

await test("blank lines are skipped", async () => {
  assert.deepEqual(await collect(streamOf(["\n\na\n\n  \nb\n"])), ["a", "b"]);
});

await test("a multi-byte character split between two chunks survives", async () => {
  const bytes = new TextEncoder().encode('{"t":"é→😀"}\n');
  // Cut inside the 4-byte emoji.
  const cut = bytes.length - 5;
  assert.deepEqual(await collect(streamOf([bytes.slice(0, cut), bytes.slice(cut)])), ['{"t":"é→😀"}']);
});

await test("lines the parser rejects are skipped", async () => {
  const kept: number[] = [];
  await readNdjson(
    streamOf(["1\nx\n2\n"]),
    (line) => (/^\d$/.test(line) ? Number(line) : null),
    (n) => kept.push(n)
  );
  assert.deepEqual(kept, [1, 2]);
});

await test("an empty stream delivers nothing", async () => {
  assert.deepEqual(await collect(streamOf([])), []);
});

await test("a throwing handler cancels the stream and surfaces the error", async () => {
  const body = streamOf(["a\n", "b\n", "c\n"]);
  await assert.rejects(
    readNdjson(body, (l) => l, (l) => {
      if (l === "b") throw new Error("handler failed");
    }),
    /handler failed/
  );
  assert.equal((body as unknown as { wasCancelled: () => boolean }).wasCancelled(), true);
});

await test("a broken connection rejects after the lines that did arrive", async () => {
  const lines: string[] = [];
  await assert.rejects(
    readNdjson(streamOf(["a\n"], new Error("network down")), (l) => l, (l) => lines.push(l)),
    /network down/
  );
  assert.deepEqual(lines, ["a"]);
});

// --- stream events -------------------------------------------------------------------------

await test("a token line is a token event", () => {
  assert.deepEqual(parseStreamEvent('{"type":"token","text":"Hel"}'), { type: "token", text: "Hel" });
});

await test("a done line carries the answer, citations, grounding and gaps", () => {
  const event = parseStreamEvent(
    JSON.stringify({
      type: "done",
      answer: "Full answer",
      sources: [{ source: "Notes", page: 3 }, { source: "Other", page: null }, { nope: 1 }],
      grounded: false,
      flagged_prerequisites: [{ id: 7, name: "Functions", extra: "ignored" }, "junk"],
    })
  );
  assert.deepEqual(event, {
    type: "done",
    answer: "Full answer",
    sources: [
      { source: "Notes", page: 3 },
      { source: "Other", page: null },
    ],
    grounded: false,
    flagged_prerequisites: [{ id: 7, name: "Functions" }],
  });
});

await test("a done line missing optional fields still parses", () => {
  assert.deepEqual(parseStreamEvent('{"type":"done","answer":"x"}'), {
    type: "done",
    answer: "x",
    sources: [],
    grounded: true,
    flagged_prerequisites: [],
  });
});

await test("an error line has a message, with a fallback", () => {
  assert.deepEqual(parseStreamEvent('{"type":"error","message":"Boom"}'), { type: "error", message: "Boom" });
  assert.deepEqual(parseStreamEvent('{"type":"error"}'), { type: "error", message: "The answer failed." });
});

await test("anything else is not an event", () => {
  for (const line of ["", "nope", "[1]", "42", "null", '{"type":"token"}', '{"type":"done"}', '{"type":"mystery"}']) {
    assert.equal(parseStreamEvent(line), null, line);
  }
});

// --- saved messages --------------------------------------------------------------------------

await test("a saved user message is a plain user message", () => {
  assert.deepEqual(fromSaved({ id: 1, role: "user", content: "Q?", sources: [], flagged: [], grounded: null }), {
    role: "user",
    text: "Q?",
  });
});

await test("a saved answer keeps its citations, gaps and grounding", () => {
  assert.deepEqual(
    fromSaved({
      id: 2,
      role: "assistant",
      content: "A.",
      sources: [{ source: "Notes", page: 1 }],
      flagged: ["Functions"],
      grounded: false,
    }),
    {
      role: "assistant",
      text: "A.",
      sources: [{ source: "Notes", page: 1 }],
      flagged: ["Functions"],
      grounded: false,
    }
  );
});

await test("a saved answer with no grounding recorded counts as grounded", () => {
  assert.equal(
    fromSaved({ id: 3, role: "assistant", content: "A.", sources: [], flagged: [], grounded: null }).grounded,
    true
  );
});

// --- maths delimiters ---------------------------------------------------------------------------

await test("\\( \\) becomes inline maths and \\[ \\] display maths", () => {
  assert.equal(normalizeMath("so \\(x^2 + 1\\) holds"), "so $x^2 + 1$ holds");
  // Display maths goes on lines of its own, which is what makes the plugin treat it as a block.
  assert.equal(normalizeMath("\\[\\frac{a}{b}\\]"), "\n$$\n\\frac{a}{b}\n$$\n");
  assert.equal(normalizeMath("\\[\na = b\n\\]"), "\n$$\na = b\n$$\n");
});

await test("maths already written with dollars is untouched", () => {
  assert.equal(normalizeMath("we have $x$ and $$y$$"), "we have $x$ and $$y$$");
});

await test("code is never rewritten", () => {
  const fenced = "```js\nconst s = '\\(not maths\\)';\n```";
  assert.equal(normalizeMath(fenced), fenced);
  assert.equal(normalizeMath("use `\\(x\\)` literally, but \\(y\\) is maths"), "use `\\(x\\)` literally, but $y$ is maths");
});

await test("an unclosed delimiter on a half-streamed answer is left alone", () => {
  assert.equal(normalizeMath("the value \\(x^"), "the value \\(x^");
  assert.equal(normalizeMath("start \\[ \\frac{1}"), "start \\[ \\frac{1}");
});

await test("text without maths is returned as it was", () => {
  const plain = "Just *markdown* with a list:\n- one\n- two";
  assert.equal(normalizeMath(plain), plain);
});

console.log(`\n${passed} passed`);
