import { pct } from "@/lib/api";

export type EvalSummary = {
  n: number;
  run_at: string;
  energy_saved_pct: number;
  quality_retained_pct: number;
  router_accuracy_pct: number;
  cache_false_hit_rate_pct: number;
  confusion: { small_small: number; small_large: number; large_small: number; large_large: number };
  method: string;
  limitations: string[];
};

export default function Evaluation({ data }: { data: EvalSummary | { error: string } | null }) {
  if (!data) return <p className="empty">Loading results.</p>;
  if ("error" in data)
    return (
      <p className="empty">
        The evaluation hasn&apos;t been run on this machine yet. Run <code>python scripts/run_eval.py</code>, then reopen this tab.
      </p>
    );
  const c = data.confusion;
  return (
    <div className="dash">
      <section className="tiles">
        <div className="tile"><span className="t-label">Energy saved</span><span className="t-num good">{pct(data.energy_saved_pct)}</span><span className="t-sub">vs all-large, {data.n} questions</span></div>
        <div className="tile"><span className="t-label">Quality retained</span><span className="t-num">{pct(data.quality_retained_pct)}</span><span className="t-sub">judged against large-model answers</span></div>
        <div className="tile"><span className="t-label">Router accuracy</span><span className="t-num">{pct(data.router_accuracy_pct)}</span><span className="t-sub">route matched the label</span></div>
        <div className="tile"><span className="t-label">Cache false hits</span><span className="t-num">{pct(data.cache_false_hit_rate_pct)}</span><span className="t-sub">trap questions served wrongly</span></div>
      </section>
      <section className="charts">
        <figure className="panel">
          <figcaption>Router decisions, label vs route</figcaption>
          <table className="confusion">
            <thead><tr><th /><th>routed small</th><th>routed large</th></tr></thead>
            <tbody>
              <tr><th>easy</th><td className="ok">{c.small_small}</td><td>{c.small_large}</td></tr>
              <tr><th>hard</th><td className="miss">{c.large_small}</td><td className="ok">{c.large_large}</td></tr>
            </tbody>
          </table>
          <p className="note">Easy sent large costs energy. Hard sent small risks quality, so escalation watches for it.</p>
        </figure>
        <div className="panel prose">
          <h3>Method</h3>
          <p>{data.method}</p>
          <h3>Limitations</h3>
          <ul>{data.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          <p className="note">Run {data.run_at}</p>
        </div>
      </section>
    </div>
  );
}
