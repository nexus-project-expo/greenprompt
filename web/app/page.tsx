"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Answer from "@/components/Answer";
import Dashboard from "@/components/Dashboard";
import Evaluation, { type EvalSummary } from "@/components/Evaluation";
import Footer from "@/components/Footer";
import History, { addToHistory, loadHistory, saveHistory, type Past } from "@/components/History";
import PowerChart from "@/components/PowerChart";
import ReceiptCard, { SampleReceipt } from "@/components/Receipt";
import { api, ERRORS, isError, sig, type ChatResult, type Stats, type Status } from "@/lib/api";

type Turn = {
  id: number;
  prompt: string;
  accuracy: boolean;
  result?: ChatResult;
  error?: string;
  time?: string;
  reported?: string;
};

type Tab = "chat" | "dashboard" | "evaluation";

const STARTERS = [
  "What is normalization in DBMS?",
  "What is 5% of 800?",
  "A shop gives 20% off and then 10% off. Is that 30% off? Show the working.",
  "What is the weather in Udupi today?",
];

function Pill({ state, children }: { state: "ok" | "warn" | "bad"; children: React.ReactNode }) {
  return <span className={`pill pill-${state}`}>{children}</span>;
}

function Pills({ s }: { s: Status | null | undefined }) {
  if (s === undefined) return null;
  if (s === null) return <div className="pills"><Pill state="bad">Server unreachable</Pill></div>;
  return (
    <div className="pills">
      {s.local_model && (
        <Pill state={s.local_model === "online" ? "ok" : s.local_model === "starting" ? "warn" : "bad"}>
          Local model: {s.local_model === "starting" ? "warming up" : s.local_model}
        </Pill>
      )}
      <Pill state={s.cloud === "online" ? "ok" : "bad"}>Cloud: {s.cloud}</Pill>
      <Pill state={s.grid ? "ok" : "warn"}>
        Grid factor: {s.grid ? `${s.grid}, ${s.grid_g_per_kwh} g/kWh` : "not set"}
      </Pill>
      {s.gpu_busy && <Pill state="warn">GPU busy: readings unreliable</Pill>}
    </div>
  );
}

function routeShort(r: ChatResult) {
  const t = r.receipt.tier;
  return t === "cache" ? "cache" : t === "small+large" ? "small, then large" : `${t} model`;
}

function chips(r: ChatResult): string[] {
  if (r.cache.hit)
    return ["cache hit", `similarity ${r.cache.similarity?.toFixed(3)}`, `same question as "${r.cache.matched_prompt}"`];
  const out = [...(r.route?.reasons ?? [])];
  if (!r.cache.cacheable) out.push(`not cached: ${r.cache.cache_reason}`);
  const n = r.cache.nearest;
  if (n?.prompt) {
    const q = n.prompt.length > 60 ? `${n.prompt.slice(0, 57)}…` : n.prompt;
    out.push(`closest cached: "${q}" (${n.why})`);
  } else if (n) {
    out.push(`no close cached question (best similarity ${n.similarity.toFixed(2)})`);
  }
  return out;
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("chat");
  const [status, setStatus] = useState<Status | null | undefined>(undefined);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [accuracy, setAccuracy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<[number, number][]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [evalData, setEvalData] = useState<EvalSummary | { error: string } | null>(null);
  const [past, setPast] = useState<Past[]>([]);
  useEffect(() => setPast(loadHistory()), []); // after mount: the static export has no localStorage at build time
  const busyRef = useRef(false);
  const t0 = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let on = true;
    const tick = async () => {
      const s = await api<Status>("/api/status", undefined, 5000);
      if (on) setStatus(isError(s) ? null : s);
    };
    tick();
    const id = setInterval(tick, 4000);
    return () => {
      on = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    const es = new EventSource("/api/power/stream");
    es.onmessage = (e) => {
      if (!busyRef.current) return;
      const d = JSON.parse(e.data) as { w: number | null; active: boolean };
      if (d.active && d.w != null) setLive((l) => [...l, [(performance.now() - t0.current) / 1000, d.w!]]);
    };
    return () => es.close();
  }, []);

  const loadStats = useCallback(async () => {
    const s = await api<Stats>("/api/stats");
    if (!isError(s)) setStats(s);
  }, []);

  useEffect(() => {
    if (tab === "dashboard") loadStats();
    if (tab === "evaluation") api<EvalSummary>("/api/eval").then(setEvalData);
  }, [tab, loadStats]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [turns]);

  const warming = status?.warm === "starting";

  async function send(text: string) {
    const prompt = text.trim();
    if (busyRef.current || warming || !prompt) return;
    const history = turns
      .slice(-3)
      .flatMap((t) => (t.result && !t.error ? [{ role: "user", content: t.prompt }, { role: "assistant", content: t.result.answer }] : []));
    const id = Date.now();
    setTurns((ts) => [...ts, { id, prompt, accuracy }]);
    setSel(id);
    setInput("");
    setLive([]);
    busyRef.current = true;
    setBusy(true);
    t0.current = performance.now();
    const res = await api<ChatResult>("/api/chat", { prompt, history, accuracy_mode: accuracy }, 150000);
    busyRef.current = false;
    setBusy(false);
    const time = new Date().toLocaleTimeString("en-GB");
    setTurns((ts) =>
      ts.map((t) =>
        t.id !== id ? t : isError(res) ? { ...t, error: res.error, time } : { ...t, result: res, error: res.error ?? undefined, time },
      ),
    );
    if (!isError(res) && !res.error) {
      const entry = { prompt, route: routeShort(res), wh: res.receipt.wh, measured: res.receipt.measured, at: Date.now() };
      setPast((p) => {
        const next = addToHistory(p, entry);
        saveHistory(next);
        return next;
      });
    }
    loadStats();
  }

  // A question from this session jumps to its answer; an older one is asked again (usually a cache hit).
  function pick(prompt: string) {
    const t = [...turns].reverse().find((x) => x.prompt === prompt && x.result && !x.error);
    if (!t) return void send(prompt);
    setSel(t.id);
    document.getElementById(`turn-${t.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function report(t: Turn) {
    const r = await api<{ reported: boolean }>("/api/report", { prompt: t.prompt });
    const msg = isError(r) ? "Couldn't report. Try again." : r.reported ? "Reported. Removed from the cache." : "Reported. It wasn't cached.";
    setTurns((ts) => ts.map((x) => (x.id === t.id ? { ...x, reported: msg } : x)));
  }

  const current = turns.find((t) => t.id === sel) ?? null;
  const pending = busy && current && !current.result && !current.error;
  const liveTrace = live.map(([t, w]) => [t - live[0][0], w] as [number, number]);

  return (
    <div className="app">
      <header className="top">
        <span className="wordmark">GreenPrompt</span>
        <nav className="tabs" aria-label="Views">
          {(["chat", "dashboard", "evaluation"] as Tab[]).map((t) => (
            <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)} aria-current={tab === t ? "page" : undefined}>
              {t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </nav>
        <Pills s={status} />
      </header>

      <div className="scroll">
      <main className="main">
        {tab === "chat" && (
          <div className="chat">
            <section className="convo">
              <div className="turns" ref={listRef}>
                {turns.length === 0 && (
                  <div className="welcome">
                    <h1>Ask a question. See what it costs.</h1>
                    <p>
                      GreenPrompt checks its cache first, then sends your question to the smallest model that can handle it, and
                      prints the energy, carbon and water bill for every answer.
                    </p>
                    <div className="starters">
                      {STARTERS.map((s) => (
                        <button key={s} onClick={() => send(s)} disabled={warming}>{s}</button>
                      ))}
                    </div>
                  </div>
                )}
                {turns.map((t) => (
                  <div key={t.id} id={`turn-${t.id}`} className={`turn${t.id === sel ? " sel" : ""}`}>
                    <p className="q">
                      {t.prompt}
                      {t.accuracy && <span className="q-flag">accuracy mode</span>}
                    </p>
                    {!t.result && !t.error && <p className="thinking">Answering…</p>}
                    {t.error && !t.result && <p className="err">{ERRORS[t.error] ?? ERRORS.internal}</p>}
                    {t.result && (
                      <>
                        {t.error ? <p className="err">{ERRORS[t.error] ?? t.result.answer}</p> : <Answer text={t.result.answer} />}
                        {!t.error && (
                          <div className="meta">
                            <button className="meta-receipt" onClick={() => setSel(t.id)} aria-pressed={t.id === sel}>
                              {routeShort(t.result)}, {sig(t.result.receipt.wh)} Wh {t.result.receipt.measured ? "measured" : "est."}
                            </button>
                            {t.reported ? <span className="muted">{t.reported}</span> : (
                              <button className="link" onClick={() => report(t)}>Report wrong answer</button>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  send(input);
                }}
              >
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(input);
                    }
                  }}
                  placeholder="Ask anything"
                  rows={2}
                  aria-label="Your question"
                />
                <div className="composer-row">
                  <label className="switch">
                    <input type="checkbox" checked={accuracy} onChange={(e) => setAccuracy(e.target.checked)} />
                    <span className="track" aria-hidden />
                    <span>
                      Accuracy mode <span className="muted">always use the large model</span>
                    </span>
                  </label>
                  <button type="submit" className="send" disabled={busy || warming || !input.trim()}>
                    {busy ? "Answering" : warming ? "Warming up" : "Ask"}
                  </button>
                </div>
              </form>
            </section>

            <aside className="side" aria-live="polite">
              {!current && (
                <>
                  <SampleReceipt />
                  <p className="hint">Ask anything to see what it costs.</p>
                </>
              )}
              {pending && (
                <>
                  <p className="hint">Working out the route…</p>
                  {liveTrace.length > 1 && <PowerChart trace={liveTrace} idle={status?.idle_w ?? null} live />}
                </>
              )}
              {current && current.error && !current.result && <p className="r-error">{ERRORS[current.error] ?? ERRORS.internal}</p>}
              {current?.result && (current.error ? (
                <p className="r-error">{ERRORS[current.error] ?? ERRORS.internal}</p>
              ) : (
                <>
                  <div className="receipt-wrap" key={current.id}>
                    <ReceiptCard result={current.result} time={current.time ?? ""} localName={status?.local_name ?? null} />
                  </div>
                  <section className="why">
                    <h2>Why this route</h2>
                    <ul className="chips">{chips(current.result).map((c) => <li key={c}>{c}</li>)}</ul>
                  </section>
                  {current.result.receipt.power_trace.length > 1 ? (
                    <PowerChart trace={current.result.receipt.power_trace} idle={current.result.receipt.idle_w} live={false} />
                  ) : current.result.receipt.tier !== "cache" ? (
                    <p className="hint">Answered in the cloud, so there is no GPU reading. Energy is estimated from published figures.</p>
                  ) : null}
                </>
              ))}
              <History
                items={past}
                onPick={pick}
                disabled={busy || warming}
                onClear={() => {
                  setPast([]);
                  saveHistory([]);
                }}
              />
            </aside>
          </div>
        )}
        {tab === "dashboard" && <Dashboard stats={stats} />}
        {tab === "evaluation" && <Evaluation data={evalData} />}
      </main>
      </div>
      <Footer />
    </div>
  );
}
