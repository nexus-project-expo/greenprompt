import { pct, sig } from "@/lib/api";

export type EvalSummary = {
  n: number;
  run_at: string;
  energy_saved_pct: number;
  gp_wh: number;
  baseline_wh: number;
  quality_retained_pct: number;
  answers_correct_pct: number;
  judged: number;
  verdicts: Record<string, number>;
  router_accuracy_pct: number;
  router_n: number;
  confusion: { small_small: number; small_large: number; large_small: number; large_large: number };
  escalation_rate_pct: number;
  paraphrase_hit_rate_pct: number;
  cache_false_hit_rate_pct: number;
  measured: number;
  estimated: number;
  tiers: Record<string, number>;
  judge_models: string[];
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
  const v = data.verdicts;
  return (
    <div className="dash">
      <section className="tiles">
        <div className="tile">
          <span className="t-label">Energy saved</span>
          <span className="t-num good">{pct(data.energy_saved_pct)}</span>
          <span className="t-sub">{sig(data.gp_wh)} Wh vs {sig(data.baseline_wh)} Wh all-large</span>
        </div>
        <div className="tile">
          <span className="t-label">Quality retained</span>
          <span className="t-num">{pct(data.quality_retained_pct)}</span>
          <span className="t-sub">as good as the large model; {pct(data.answers_correct_pct)} correct</span>
        </div>
        <div className="tile">
          <span className="t-label">Router accuracy</span>
          <span className="t-num">{pct(data.router_accuracy_pct)}</span>
          <span className="t-sub">{data.router_n} labelled questions; {pct(data.escalation_rate_pct)} escalated</span>
        </div>
        <div className="tile">
          <span className="t-label">Cache false hits</span>
          <span className={`t-num${data.cache_false_hit_rate_pct === 0 ? " good" : ""}`}>{pct(data.cache_false_hit_rate_pct)}</span>
          <span className="t-sub">on 10 traps; {pct(data.paraphrase_hit_rate_pct)} of paraphrases hit</span>
        </div>
      </section>
      <p className="note">
        {data.n} questions. {data.judged} answers not from the large model were judged by {data.judge_models.join(", ")}:{" "}
        {v.better ?? 0} better, {v.same ?? 0} same, {v.worse ?? 0} worse. {data.measured} receipts measured on the GPU,{" "}
        {data.estimated} estimated.
      </p>
      <section className="charts">
        <figure className="panel">
          <figcaption>Router decisions, label vs route</figcaption>
          <table className="confusion">
            <thead><tr><th /><th>routed small</th><th>routed large</th></tr></thead>
            <tbody>
              <tr><th>labelled easy</th><td className="ok">{c.small_small}</td><td>{c.small_large}</td></tr>
              <tr><th>labelled hard</th><td className="miss">{c.large_small}</td><td className="ok">{c.large_large}</td></tr>
            </tbody>
          </table>
          <p className="note">Easy sent large wastes energy. Hard sent small risks quality, which escalation watches for.</p>
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
