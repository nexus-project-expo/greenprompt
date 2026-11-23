/** GPU watts over time. The shaded area above the dashed idle line is the energy we count. */
export default function PowerChart({ trace, idle, live }: { trace: [number, number][]; idle: number | null; live: boolean }) {
  const W = 400, H = 130, PAD = 6;
  if (trace.length < 2) return null;
  const tMax = Math.max(trace[trace.length - 1][0], 0.5);
  const ws = trace.map((p) => p[1]);
  const lo = Math.min(...ws, idle ?? Infinity) - 3;
  const hi = Math.max(...ws, (idle ?? 0) + 10) + 3;
  const x = (t: number) => PAD + (t / tMax) * (W - 2 * PAD);
  const y = (w: number) => H - PAD - ((w - lo) / (hi - lo)) * (H - 2 * PAD);
  const line = trace.map(([t, w], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(w).toFixed(1)}`).join("");
  const iy = idle != null ? y(idle) : null;
  const area =
    iy != null
      ? `M${x(trace[0][0])},${iy}` +
        trace.map(([t, w]) => `L${x(t).toFixed(1)},${y(Math.max(w, idle!)).toFixed(1)}`).join("") +
        `L${x(trace[trace.length - 1][0])},${iy}Z`
      : "";
  const peak = Math.max(...ws);
  return (
    <figure className="power">
      <figcaption>
        <span>GPU power{live ? ", live" : ""}</span>
        <span className="mono">
          peak {peak.toFixed(0)} W{idle != null && <>, idle {idle.toFixed(1)} W</>}, {tMax.toFixed(1)} s
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`GPU power over ${tMax.toFixed(1)} seconds, peak ${peak.toFixed(0)} watts`}>
        {area && <path d={area} className="p-area" />}
        {iy != null && <line x1={PAD} x2={W - PAD} y1={iy} y2={iy} className="p-idle" />}
        <path d={line} className="p-line" />
      </svg>
    </figure>
  );
}
