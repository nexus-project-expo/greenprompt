import { sig } from "@/lib/api";

export type Past = { prompt: string; route: string; wh: number; measured: boolean; at: number };

const KEY = "greenprompt-history";
const MAX = 15;

// Kept in this browser only: the server log stores a hash of each prompt, never the text, so one person's
// questions are never shown to anyone else using the same server.
export function loadHistory(): Past[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.slice(0, MAX) : [];
  } catch {
    return [];
  }
}

export function saveHistory(items: Past[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(items.slice(0, MAX)));
  } catch {
    /* private window or storage blocked: history just isn't kept */
  }
}

export function addToHistory(items: Past[], p: Past): Past[] {
  const key = p.prompt.trim().toLowerCase();
  return [p, ...items.filter((x) => x.prompt.trim().toLowerCase() !== key)].slice(0, MAX);
}

export default function History({ items, onPick, onClear, disabled }: {
  items: Past[];
  onPick: (prompt: string) => void;
  onClear: () => void;
  disabled: boolean;
}) {
  if (!items.length) return null;
  return (
    <section className="history" aria-label="Your questions">
      <div className="history-head">
        <h2>Your questions</h2>
        <button className="link" onClick={onClear}>Clear</button>
      </div>
      <ul>
        {items.map((h) => (
          <li key={h.prompt}>
            <button onClick={() => onPick(h.prompt)} disabled={disabled} title={h.prompt}>
              <span className="h-q">{h.prompt}</span>
              <span className="h-meta">{h.route}, {sig(h.wh)} Wh {h.measured ? "measured" : "est."}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
