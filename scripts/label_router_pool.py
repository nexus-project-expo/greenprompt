"""Label router training questions by experiment instead of by opinion.

For each question in data/router_pool.txt: the local small model answers, the large model answers, and the
evaluation's blind judge compares them. Small answer as good and correct -> "easy", otherwise "hard".
Writes data/router_measured.csv, which scripts/train_router.py adds to the hand-written training set.

    python scripts/label_router_pool.py      # resumable: rerun after a rate-limit stop and it continues
"""
import csv
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval  # noqa: E402  (also paces large-model calls to the free-tier token budget)
from greenprompt import config, embedder, models, pipeline  # noqa: E402

POOL = config.DATA_DIR / "router_pool.txt"
OUT = config.DATA_DIR / "router_measured.csv"
STATE = config.RESULTS_DIR / "label_state.json"
NEAR_DUP = 0.95  # same rule as train_router.py: nothing this close to an eval question may be trained on


def ask(ep, tier, prompt):
    msgs = [pipeline.SYSTEM, {"role": "user", "content": prompt}]
    for wait in (0, 20, 40, 60):
        time.sleep(wait)
        r = models.call(ep, tier, msgs, retries=1, timeout=180)
        if r.ok and r.text.strip():
            return r.text
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pool = list(dict.fromkeys(l.strip() for l in POOL.read_text(encoding="utf-8").splitlines() if l.strip()))
    evalq = [r["prompt"] for r in csv.DictReader(open(config.DATA_DIR / "eval_questions.csv", encoding="utf-8"))]
    P, E = embedder.embed(pool), embedder.embed(evalq)
    keep = [p for p, s in zip(pool, (P @ E.T).max(1)) if s < NEAR_DUP]
    print(f"{len(pool)} pool questions, {len(pool) - len(keep)} dropped as too close to an eval question")

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    rng = random.Random(7)
    todo = [p for p in keep if p not in state]
    print(f"{len(keep) - len(todo)} already labelled, {len(todo)} to go")
    for i, p in enumerate(todo, 1):
        small, large = ask(config.OLLAMA, "small", p), ask(config.LARGE, "large", p)
        if small is None or large is None:
            print("A model keeps failing (daily limit or Ollama down). Progress is saved; rerun to resume.")
            break
        j = run_eval.judge_one(p, small, large, rng)
        if j is None:
            print("Judge keeps failing (daily limit?). Progress is saved; rerun to resume.")
            break
        easy = j["verdict"] in ("same", "better") and j["gp_ok"]
        state[p] = {"label": "easy" if easy else "hard", "verdict": j["verdict"], "small_ok": j["gp_ok"],
                    "reason": j["raw"]}
        STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
        print(f"  {i}/{len(todo)} {state[p]['label']:4} ({j['verdict']}, small ok={j['gp_ok']})  {p[:70]}")
        time.sleep(run_eval.JUDGE_GAP_S)

    rows = [{"prompt": p, "label": s["label"], "judge_verdict": s["verdict"], "small_correct": s["small_ok"]}
            for p, s in state.items() if p in keep]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["prompt", "label", "judge_verdict", "small_correct"])
        w.writeheader()
        w.writerows(rows)
    easy = sum(r["label"] == "easy" for r in rows)
    print(f"Wrote {OUT.name}: {len(rows)} rows, {easy} easy, {len(rows) - easy} hard")
    return 0


if __name__ == "__main__":
    sys.exit(main())
