import type { ChatResult } from "@/lib/api";
import { pct, sig } from "@/lib/api";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="r-row">
      <span>{label}</span>
      <span className="r-dots" aria-hidden />
      <span className="r-val">{children}</span>
    </div>
  );
}

function Tag({ measured, sources }: { measured: boolean; sources?: string[] }) {
  return measured ? (
    <span className="tag tag-measured">measured</span>
  ) : (
    <span className="tag tag-est" title={sources?.join("\n")}>est.</span>
  );
}

function routeLabel(r: ChatResult["receipt"], localName: string | null) {
  if (r.tier === "cache") return "cache, no model";
  if (r.tier === "small+large") return "small, then large";
  if (r.tier === "error") return "no answer";
  const where = r.model && r.model === localName ? "local" : "cloud";
  return `${r.tier} (${where})`;
}

export default function ReceiptCard({ result, time, localName }: { result: ChatResult; time: string; localName: string | null }) {
  const r = result.receipt;
  const ranged = !r.measured && r.wh_high > r.wh_low;
  return (
    <article className="receipt" aria-label="Carbon receipt for this answer">
      <header className="r-head">
        <span>GREENPROMPT RECEIPT</span>
        <span>{time}</span>
      </header>
      <Row label="route">{routeLabel(r, localName)}</Row>
      {r.model && <Row label={r.tier === "cache" ? "cached from" : "model"}>{r.model}</Row>}
      <Row label="energy">
        {sig(r.wh)} Wh <Tag measured={r.measured} sources={r.sources} />
      </Row>
      {ranged && (
        <Row label="range">
          {sig(r.wh_low)} to {sig(r.wh_high)} Wh
        </Row>
      )}
      <Row label="vs large model">
        ~{sig(r.baseline_wh)} Wh <Tag measured={false} sources={r.sources} />
      </Row>
      <Row label="saved">
        <span className={r.saved_wh >= 0 ? "good" : r.escalated ? "bad" : ""}>
          {r.saved_wh >= 0 || !r.escalated ? pct(Math.max(0, r.saved_pct)) : `${pct(r.saved_pct)} (escalation cost extra)`}
        </span>
      </Row>
      <Row label="CO2">{sig(r.g_co2)} g</Row>
      <Row label="water (on-site)">{sig(r.ml_water)} mL</Row>
      <Row label="latency">{r.latency_s < 0.1 ? `${Math.round(r.latency_s * 1000)} ms` : `${r.latency_s.toFixed(2)} s`}</Row>
      <footer className="r-foot">
        {r.grid_note && <p>{r.grid_note}</p>}
        <details>
          <summary>Sources</summary>
          <ul>
            {r.sources.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </details>
      </footer>
    </article>
  );
}

export function SampleReceipt() {
  return (
    <article className="receipt receipt-sample" aria-hidden>
      <header className="r-head">
        <span>GREENPROMPT RECEIPT</span>
        <span>--:--:--</span>
      </header>
      <Row label="route">small (local)</Row>
      <Row label="energy">0.012 Wh</Row>
      <Row label="vs large model">~0.24 Wh</Row>
      <Row label="saved">95%</Row>
      <Row label="CO2">0.008 g</Row>
      <Row label="latency">0.8 s</Row>
    </article>
  );
}
