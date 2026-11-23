import type { Stats } from "@/lib/api";
import { pct, sig } from "@/lib/api";

const TIERS: [string, string][] = [
  ["cache", "Cache"],
  ["small", "Small model"],
  ["large", "Large model"],
  ["small+large", "Escalated"],
];

function Cumulative({ data: rows }: { data: Stats["cumulative"] }) {
  const data = [{ ts: 0, wh: 0, baseline_wh: 0 }, ...rows];
  const W = 640, H = 220, L = 44, B = 24, T = 10, R = 10;
  const max = Math.max(...data.map((d) => d.baseline_wh), ...data.map((d) => d.wh), 0.001);
  const n = Math.max(data.length, 2);
  const x = (i: number) => L + (i / (n - 1)) * (W - L - R);
  const y = (v: number) => H - B - (v / max) * (H - B - T);
  const path = (k: "wh" | "baseline_wh") => data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d[k]).toFixed(1)}`).join("");
  const ticks = [0, max / 2, max];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Cumulative energy, GreenPrompt against all-large baseline">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="grid" />
          <text x={L - 6} y={y(t) + 4} textAnchor="end" className="axis">{sig(t, 2)}</text>
        </g>
      ))}
      <text x={W - R} y={H - 6} textAnchor="end" className="axis">{rows.length} requests</text>
      <path d={path("baseline_wh")} className="c-base" />
      <path d={path("wh")} className="c-ours" />
    </svg>
  );
}

export default function Dashboard({ stats }: { stats: Stats | null }) {
  if (!stats) return <p className="empty">Loading the request log.</p>;
  if (!stats.requests) return <p className="empty">No requests yet. Ask something in the Chat tab and the totals start here.</p>;
  const total = stats.requests;
  const avgBase = stats.baseline_wh / total;
  return (
    <div className="dash">
      <section className="tiles">
        <div className="tile">
          <span className="t-label">Requests</span>
          <span className="t-num">{total}</span>
          <span className="t-sub">{stats.measured} measured on the GPU</span>
        </div>
        <div className="tile">
          <span className="t-label">Cache hit rate</span>
          <span className="t-num">{pct(100 * stats.cache_hit_rate)}</span>
          <span className="t-sub">{stats.tiers.cache} answered without a model</span>
        </div>
        <div className="tile">
          <span className="t-label">Energy saved</span>
          <span className="t-num good">{sig(stats.saved_wh)}<small> Wh</small></span>
          <span className="t-sub">{pct(stats.saved_pct)} of {sig(stats.baseline_wh)} Wh baseline</span>
        </div>
        <div className="tile">
          <span className="t-label">CO2 avoided</span>
          <span className="t-num good">{sig(stats.g_co2_saved)}<small> g</small></span>
          <span className="t-sub">{sig(stats.g_co2)} g emitted</span>
        </div>
      </section>
      <p className="note">
        Savings compare against sending every request to the large model, estimated at ~{sig(avgBase)} Wh each
        <span className="tag tag-est">est.</span>. Local answers are measured; cloud answers are estimated.
      </p>
      <section className="charts">
        <figure className="panel">
          <figcaption>
            Cumulative energy, Wh
            <span className="legend">
              <i className="k-ours" /> GreenPrompt <i className="k-base" /> all-large baseline
            </span>
          </figcaption>
          <Cumulative data={stats.cumulative} />
        </figure>
        <figure className="panel">
          <figcaption>Where requests went</figcaption>
          <div className="stack" role="img" aria-label="Share of requests by route">
            {TIERS.map(([k]) =>
              stats.tiers[k] ? <span key={k} className={`s-${k.replace("+", "-")}`} style={{ flexGrow: stats.tiers[k] }} /> : null,
            )}
          </div>
          <table className="tier-table">
            <thead>
              <tr><th>Route</th><th>Requests</th><th>Share</th><th>Median latency</th></tr>
            </thead>
            <tbody>
              {TIERS.map(([k, label]) => (
                <tr key={k}>
                  <td><i className={`key s-${k.replace("+", "-")}`} />{label}</td>
                  <td>{stats.tiers[k]}</td>
                  <td>{pct((100 * stats.tiers[k]) / total)}</td>
                  <td>{stats.median_latency_s[k] == null ? "–" : `${stats.median_latency_s[k]!.toFixed(2)} s`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </figure>
      </section>
    </div>
  );
}
