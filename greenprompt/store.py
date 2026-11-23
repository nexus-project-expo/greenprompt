"""SQLite request log that feeds the dashboard. Stores a hash of each prompt, never the raw text."""
import hashlib
import sqlite3
import time
from pathlib import Path

from greenprompt import config

SCHEMA = """CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, prompt_hash TEXT NOT NULL, tier TEXT NOT NULL, model TEXT,
    p_hard REAL, escalated INTEGER NOT NULL, cache_hit INTEGER NOT NULL, wh REAL NOT NULL, g_co2 REAL NOT NULL,
    ml_water REAL NOT NULL, baseline_wh REAL NOT NULL, latency_s REAL NOT NULL, measured INTEGER NOT NULL,
    ok INTEGER NOT NULL DEFAULT 1)"""


class Store:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = str(db_path or config.DB_PATH)
        with self._db() as db:
            db.execute(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5)

    def log_request(self, prompt: str, receipt, p_hard: float | None, cache_hit: bool, ok: bool) -> None:
        h = hashlib.sha256(prompt.strip().lower().encode()).hexdigest()[:16]
        with self._db() as db:
            db.execute("INSERT INTO requests (ts, prompt_hash, tier, model, p_hard, escalated, cache_hit, wh, g_co2, "
                       "ml_water, baseline_wh, latency_s, measured, ok) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (time.time(), h, receipt.tier, receipt.model, p_hard, int(receipt.escalated), int(cache_hit),
                        receipt.wh, receipt.g_co2, receipt.ml_water, receipt.baseline_wh, receipt.latency_s,
                        int(receipt.measured), int(ok)))

    def stats(self) -> dict:
        """Totals since the log started, for the dashboard. Failed requests are excluded."""
        with self._db() as db:
            rows = db.execute("SELECT ts, tier, wh, g_co2, ml_water, baseline_wh, latency_s, measured, cache_hit "
                              "FROM requests WHERE ok = 1 ORDER BY ts").fetchall()
        n = len(rows)
        tiers = {t: sum(r[1] == t for r in rows) for t in ("cache", "small", "large", "small+large")}
        wh, base = sum(r[2] for r in rows), sum(r[5] for r in rows)
        latency = {}
        for t in tiers:
            ls = sorted(r[6] for r in rows if r[1] == t)
            latency[t] = ls[len(ls) // 2] if ls else None
        cum, a, b = [], 0.0, 0.0
        for r in rows:
            a, b = a + r[2], b + r[5]
            cum.append({"ts": r[0], "wh": round(a, 6), "baseline_wh": round(b, 6)})
        return {
            "requests": n,
            "cache_hit_rate": tiers["cache"] / n if n else 0.0,
            "small_share": (tiers["small"]) / n if n else 0.0,
            "tiers": tiers,
            "wh": wh, "baseline_wh": base, "saved_wh": base - wh,
            "saved_pct": 100 * (base - wh) / base if base else 0.0,
            "g_co2": sum(r[3] for r in rows),
            "g_co2_saved": (base - wh) / 1000 * config.GRID_EF_G_PER_KWH,
            "ml_water": sum(r[4] for r in rows),
            "measured": sum(r[7] for r in rows),
            "median_latency_s": latency,
            "cumulative": cum,
        }

    def clear(self) -> None:
        with self._db() as db:
            db.execute("DELETE FROM requests")
