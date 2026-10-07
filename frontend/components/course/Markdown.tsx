"use client";

import "katex/dist/katex.min.css";

import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { normalizeMath } from "@/lib/chat";

// Renders a tutor answer: markdown (lists, tables, emphasis), maths ($..$ and
// $$..$$, plus the \( \) and \[ \] models like to write) and syntax-highlighted
// code. Raw HTML in the text is not rendered (react-markdown's default), so an
// answer that repeats something from an uploaded file can't inject markup, and
// links only open as ordinary http(s)/mailto links in a new tab.
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, [rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
        }}
      >
        {normalizeMath(children)}
      </ReactMarkdown>
    </div>
  );
}
