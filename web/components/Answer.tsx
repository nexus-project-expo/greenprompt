import { Fragment } from "react";

// shortcut: covers the markdown models actually emit (code, bold, italics, lists, headings, tables); swap for react-markdown if more is needed.
// An italic * must not touch a word, so plain-text maths like 2*3*4 stays as written.
function inline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|(?<![\w*])\*[^*\s](?:[^*]*[^*\s])?\*(?![\w*]))/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 3) return <strong key={i}>{inline(part.slice(2, -2))}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 1) return <code key={i}>{part.slice(1, -1)}</code>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{inline(part.slice(1, -1))}</em>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

// Models write LaTeX even when asked not to; show it as readable plain text.
function untex(s: string) {
  const sym: Record<string, string> = {
    times: "×", cdot: "·", div: "÷", le: "≤", leq: "≤", ge: "≥", geq: "≥", neq: "≠", approx: "≈", pm: "±",
    rightarrow: "→", to: "→", Rightarrow: "⇒", Longrightarrow: "⇒", implies: "⇒", iff: "⇔", infty: "∞", pi: "π",
    quad: "  ", qquad: "  ", left: "", right: "", gcd: "gcd", log: "log", ln: "ln", sin: "sin", cos: "cos", tan: "tan",
  };
  return s
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => "\n```\n" + m.trim() + "\n```\n")
    .replace(/\\\(([\s\S]+?)\\\)/g, "`$1`")
    .replace(/([_^])\{([^{}]*)\}/g, "$1$2") // flatten p^{2} first so \frac{p^{2}}{q^{2}} has no nested braces
    .replace(/\\(?:text|mathrm|mathbf|operatorname)\{([^{}]*)\}/g, "$1") // before \frac, which needs brace-free parts
    .replace(/\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}/g, "($1)/($2)")
    .replace(/\\sqrt\{([^{}]*)\}/g, "√($1)")
    .replace(/\\sqrt\s*/g, "√")
    .replace(/\\([a-zA-Z]+)/g, (m, w) => sym[w] ?? m)
    .replace(/\\([%$,;!])/g, (_, c) => (c === "%" || c === "$" ? c : " "));
}

// A markdown table: header row, then a |---|---| separator, then body rows. Captured so split() keeps it.
// Separator cells are bounded by "|" so the dash runs can't overlap (no catastrophic backtracking).
const TABLE = /(^\|.*\|[ \t]*\n\|(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*(?:\n\|.*\|[ \t]*)*)/m;

function Table({ src }: { src: string }) {
  const rows = src.trim().split("\n").map((r) =>
    r.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|")));
  const [head, , ...body] = rows;
  const cell = (c: string) =>
    c.split(/<br\s*\/?>/i).map((s, n) => <Fragment key={n}>{n > 0 && <br />}{inline(s)}</Fragment>);
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{head.map((c, j) => <th key={j}>{cell(c)}</th>)}</tr></thead>
        <tbody>{body.map((r, j) => <tr key={j}>{r.map((c, m) => <td key={m}>{cell(c)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
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
    let start = 1; // keep the model's numbering when a code block splits a numbered list
    const flush = (k: string) => {
      if (!list.length) return;
      const items = list.map((l, j) => <li key={j}>{inline(l)}</li>);
      blocks.push(ordered ? <ol key={k} start={start}>{items}</ol> : <ul key={k}>{items}</ul>);
      list = [];
    };
    chunk.split(TABLE).forEach((seg, t) => {
    if (t % 2 === 1) {
      flush(`${i}-${t}f`);
      blocks.push(<Table key={`${i}-t${t}`} src={seg} />);
      return;
    }
    seg.split(/\n{2,}|\n(?=\s*(?:[-*]|\d+\.)\s)|\n(?=#)/).forEach((para, j) => {
      const k = `${i}-${t}-${j}`;
      const p = para.trim();
      if (!p) return;
      if (/^([-*_])\1{2,}$/.test(p)) {
        flush(k + "f");
        blocks.push(<hr key={k} />);
        return;
      }
      const item = p.match(/^(?:[-*]|(\d+)\.)\s+([\s\S]*)/);
      if (item) {
        if (list.length && ordered !== !!item[1]) flush(k + "f");
        ordered = !!item[1];
        if (!list.length && item[1]) start = Number(item[1]);
        list.push(item[2]);
        return;
      }
      flush(k + "f");
      const h = p.match(/^#{1,6}\s+(.*)(?:\n([\s\S]*))?/);
      if (!h) {
        blocks.push(<p key={k}>{inline(p)}</p>);
        return;
      }
      blocks.push(<h4 key={k}>{inline(h[1])}</h4>);
      if (h[2]?.trim()) blocks.push(<p key={`${k}b`}>{inline(h[2].trim())}</p>); // text right under the heading
    });
    });
    flush(`${i}-end`);
  });
  return <div className="answer">{blocks}</div>;
}
