import { Fragment } from "react";

// shortcut: covers the markdown small models actually emit (code, bold, lists, headings); swap for react-markdown if tables matter.
function inline(text: string) {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 1) return <code key={i}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 3) return <strong key={i}>{part.slice(2, -2)}</strong>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

// Models write LaTeX even when asked not to; show it as readable plain text.
function untex(s: string) {
  const sym: Record<string, string> = { times: "×", cdot: "·", div: "÷", le: "≤", ge: "≥", neq: "≠", approx: "≈", rightarrow: "→", quad: "  ", qquad: "  " };
  return s
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => "\n```\n" + m.trim() + "\n```\n")
    .replace(/\\\(([\s\S]+?)\\\)/g, "`$1`")
    .replace(/\\([a-zA-Z]+)/g, (m, w) => sym[w] ?? m)
    .replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, "($1)/($2)")
    .replace(/\\(?:text|mathrm|mathbf|operatorname)\{([^{}]*)\}/g, "$1")
    .replace(/\\([%$,;!])/g, (_, c) => (c === "%" || c === "$" ? c : " "));
}

export default function Answer({ text: raw }: { text: string }) {
  const text = untex(raw);
  const blocks: React.ReactNode[] = [];
  const parts = text.split(/```[^\n]*\n?/);
  parts.forEach((chunk, i) => {
    if (i % 2 === 1) {
      blocks.push(<pre key={`c${i}`}><code>{chunk.replace(/\n$/, "")}</code></pre>);
      return;
    }
    let list: string[] = [];
    let ordered = false;
    const flush = (k: string) => {
      if (!list.length) return;
      const items = list.map((l, j) => <li key={j}>{inline(l)}</li>);
      blocks.push(ordered ? <ol key={k}>{items}</ol> : <ul key={k}>{items}</ul>);
      list = [];
    };
    chunk.split(/\n{2,}|\n(?=\s*(?:[-*]|\d+\.)\s)|\n(?=#)/).forEach((para, j) => {
      const k = `${i}-${j}`;
      const p = para.trim();
      if (!p) return;
      const item = p.match(/^(?:[-*]|(\d+)\.)\s+([\s\S]*)/);
      if (item) {
        if (list.length && ordered !== !!item[1]) flush(k + "f");
        ordered = !!item[1];
        list.push(item[2]);
        return;
      }
      flush(k + "f");
      const h = p.match(/^#{1,6}\s+(.*)/);
      blocks.push(h ? <h4 key={k}>{inline(h[1])}</h4> : <p key={k}>{inline(p)}</p>);
    });
    flush(`${i}-end`);
  });
  return <div className="answer">{blocks}</div>;
}
