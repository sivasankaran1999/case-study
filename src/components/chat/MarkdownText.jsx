import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const components = {
  p: ({ children }) => (
    <p className="mb-2.5 last:mb-0 leading-relaxed">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-ps-text">{children}</strong>
  ),
  em: ({ children }) => <em className="italic text-ps-textMuted">{children}</em>,
  ul: ({ children }) => (
    <ul className="mb-2.5 space-y-2 last:mb-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2.5 list-decimal space-y-2 pl-5 last:mb-0">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="relative pl-4 leading-relaxed before:absolute before:left-0 before:top-[0.55em] before:h-1.5 before:w-1.5 before:rounded-full before:bg-ps-teal/70">
      {children}
    </li>
  ),
  h1: ({ children }) => (
    <h3 className="mb-2 text-sm font-bold text-ps-text">{children}</h3>
  ),
  h2: ({ children }) => (
    <h3 className="mb-2 text-sm font-bold text-ps-text">{children}</h3>
  ),
  h3: ({ children }) => (
    <h4 className="mb-1.5 text-sm font-semibold text-ps-text">{children}</h4>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-ps-teal underline underline-offset-2 hover:text-ps-tealDark"
    >
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded-md bg-ps-tealSoft px-1.5 py-0.5 font-mono text-[0.78em] font-medium text-ps-tealDark">
      {children}
    </code>
  ),
  hr: () => <hr className="my-3 border-ps-border" />,
};

const MarkdownText = ({ children }) => (
  <div className="markdown-body text-[15px] text-ps-text">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children || ""}
    </ReactMarkdown>
  </div>
);

export default MarkdownText;
