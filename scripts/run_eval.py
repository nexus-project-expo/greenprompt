"""The ~100-question evaluation from docs/EVALUATION.md.

1. Baseline: every prompt straight to the large model (answers cached in results/eval_state.json).
2. GreenPrompt: every prompt through the full pipeline, fresh cache, in file order.
3. Judge: where GreenPrompt did not use the large model, a judge from a different model family
   compares its answer with the baseline answer, in random order.

Resumable: rerun after a rate-limit stop and it continues. `--fresh` reruns steps 2-3 but keeps the baseline.
Writes results/eval_summary.json (read by the UI), results/eval_rows.csv and results/judge_handcheck.csv.
"""
import argparse
import collections
import csv
import json
import random
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # model text can hold characters cp1252 can't print

from greenprompt import config, energy, models, pipeline  # noqa: E402
from greenprompt.cache import SemanticCache  # noqa: E402
from greenprompt.router import Router  # noqa: E402
from greenprompt.store import Store  # noqa: E402

RES = config.RESULTS_DIR
STATE = RES / "eval_state.json"
CACHE_DB = RES / "eval_cache.db"
LOG_DB = RES / "eval_log.db"
TPM_BUDGET = 7000  # Groq free tier allows 8000 tokens/min for gpt-oss-120b (read from response headers, 23 Nov 2026)
JUDGE_GAP_S = 4.5

# ---------- rate limiting for the large model ----------
_used: collections.deque = collections.deque()
_waited = [0.0]  # seconds spent waiting for the rate limit, subtracted from reported latency
_real_call = models.call


def _paced_call(ep, tier, messages, retries=1, timeout=None):
    if ep == config.LARGE:
        while True:
            now = time.monotonic()
            while _used and now - _used[0][0] > 60:
                _used.popleft()
            if sum(t for _, t in _used) + 1500 <= TPM_BUDGET:
                break
            time.sleep(1)
            _waited[0] += 1
    r = _real_call(ep, tier, messages, retries, timeout)
    if ep == config.LARGE:
        _used.append((time.monotonic(), (r.prompt_tokens or 0) + (r.completion_tokens or 0) or 1500))
    return r


models.call = _paced_call  # models.chat looks up call at runtime, so pipeline calls are paced too


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"baseline": {}, "pipeline": {}, "judge": {}}


def save_state(s: dict):
    STATE.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")


def questions() -> list[dict]:
    with open(config.DATA_DIR / "eval_questions.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------- 1. baseline ----------

def run_baseline(qs, state):
    todo = [q for q in qs if q["id"] not in state["baseline"]]
    print(f"baseline: {len(qs) - len(todo)} cached, {len(todo)} to run")
    for i, q in enumerate(todo, 1):
        msgs = [pipeline.SYSTEM, {"role": "user", "content": q["prompt"]}]
        for wait in (0, 20, 40, 60):
            time.sleep(wait)
            r = models.call(config.LARGE, "large", msgs)
            if r.ok:
                break
            print(f"  #{q['id']} failed ({r.error[:120]}), waiting")
        if not r.ok:
            print("Large model keeps failing (daily limit?). Progress is saved; rerun later to resume.")
            save_state(state)
            sys.exit(2)
        state["baseline"][q["id"]] = {"answer": r.text, "model": r.model,
                                      "tokens": (r.prompt_tokens or 0) + (r.completion_tokens or 0)}
        if i % 5 == 0 or i == len(todo):
            save_state(state)
            print(f"  {i}/{len(todo)}")


# ---------- 2. GreenPrompt ----------

def run_pipeline(qs, state):
    pipeline._parts.update(cache=SemanticCache(CACHE_DB), router=Router(), store=Store(LOG_DB))
    todo = [q for q in qs if q["id"] not in state["pipeline"]]
    print(f"pipeline: {len(qs) - len(todo)} done, {len(todo)} to run")
    if todo:
        print("  warm-up:", pipeline.warm_up())
    for q in todo:
        w0 = _waited[0]
        answer, r, d, info = pipeline.handle_prompt(q["prompt"])
        r.latency_s -= _waited[0] - w0
        if info.get("error"):
            print(f"  #{q['id']} no answer ({info['error']}). Progress saved; rerun to resume.")
            save_state(state)
            sys.exit(2)
        state["pipeline"][q["id"]] = {
            "answer": answer, "tier": r.tier, "routed": d.tier if d else None, "p_hard": d.p_hard if d else None,
            "reasons": d.reasons if d else [], "cache_hit": info["hit"], "similarity": info.get("similarity"),
            "matched_prompt": info.get("matched_prompt"), "wh": r.wh, "baseline_wh": r.baseline_wh,
            "g_co2": r.g_co2, "measured": r.measured, "latency_s": r.latency_s, "model": r.model,
            "escalated": r.escalated}
        save_state(state)
        print(f"  #{q['id']:>3} {r.tier:<11} {r.wh:.4f} Wh {'M' if r.measured else 'e'} {r.latency_s:5.2f}s  {q['prompt'][:50]}")


# ---------- 3. judge ----------

JUDGE_PROMPT = """You are grading two answers to the same question.

Question:
{q}

Answer A:
{a}

Answer B:
{b}

Decide which answer serves the person who asked better. Correctness matters most. If both are correct and \
answer the question adequately, they are EQUAL, even if one is longer or more detailed.
Also say whether each answer, on its own, is correct and adequately answers the question.

Reply in exactly this format:
VERDICT: A, B or EQUAL
A_OK: yes or no
B_OK: yes or no
REASON: at most 20 words"""


def judge_one(q, gp, base, rng):
    swap = rng.random() < 0.5
    a, b = (base, gp) if swap else (gp, base)
    msgs = [{"role": "user", "content": JUDGE_PROMPT.format(q=q, a=a[:6000], b=b[:6000])}]
    # One judge only (no fallback to the large model, which would grade its own answers); wait out rate limits.
    for wait in (0, 15, 30, 60):
        time.sleep(wait)
        r = models.call(config.JUDGE, "judge", msgs, retries=0)
        if not r.ok:
            continue
        f = dict(re.findall(r"^\W*(VERDICT|A_OK|B_OK|REASON)\W*:\s*\**(.+?)\**\s*$", r.text, re.M | re.I))
        f = {k.upper(): v.strip() for k, v in f.items()}
        word = f.get("VERDICT", "").split()[0].strip("*.,").upper() if f.get("VERDICT") else ""
        gp_letter = "B" if swap else "A"
        ok = f.get(f"{gp_letter}_OK", "").lower()
        base_ok = f.get(f"{'A' if gp_letter == 'B' else 'B'}_OK", "").lower()
        if word in ("A", "B", "EQUAL") and ok[:3] in ("yes", "no"):
            verdict = "same" if word == "EQUAL" else ("better" if word == gp_letter else "worse")
            # The judge sometimes contradicts itself; its per-answer correctness flags win.
            if ok.startswith("no") and base_ok.startswith("yes"):
                verdict = "worse"
            elif ok.startswith("yes") and base_ok.startswith("no"):
                verdict = "better"
            return {"verdict": verdict, "gp_ok": ok.startswith("yes"), "raw": f.get("REASON", "")[:300],
                    "judge": r.model, "gp_was": gp_letter}
    return None


def run_judge(qs, state):
    rng = random.Random(7)
    for k in [k for k, v in state["judge"].items() if v["judge"] != config.JUDGE.model]:
        del state["judge"][k]  # re-judge anything a fallback judge graded
    todo = [q for q in qs if state["pipeline"].get(q["id"], {}).get("tier") not in (None, "large", "small+large")
            and q["id"] not in state["judge"]]
    print(f"judge: {len(todo)} to run")
    for q in todo:
        v = judge_one(q["prompt"], state["pipeline"][q["id"]]["answer"], state["baseline"][q["id"]]["answer"], rng)
        if v is None:
            print(f"  #{q['id']} judge failed, will retry on the next run")
        else:
            state["judge"][q["id"]] = v
            save_state(state)
            print(f"  #{q['id']:>3} {v['verdict']:<6} {v['raw'][:90]}")
        time.sleep(JUDGE_GAP_S)


# ---------- summary ----------

def summarise(qs, state) -> dict:
    rows = []
    for q in qs:
        p, b, j = state["pipeline"].get(q["id"]), state["baseline"].get(q["id"]), state["judge"].get(q["id"])
        if not p or not b:
            continue
        if p["tier"] in ("large", "small+large"):
            verdict = "large model"  # the large model answered, so quality equals the baseline by construction
        else:
            verdict = j["verdict"] if j else "unjudged"
        rows.append({**q, **{k: p[k] for k in ("tier", "routed", "p_hard", "cache_hit", "similarity", "matched_prompt",
                                                "wh", "baseline_wh", "measured", "latency_s", "model", "escalated")},
                     "verdict": verdict, "gp_ok": bool(j and j.get("gp_ok")), "judge_reason": j["raw"] if j else "", "answer": p["answer"],
                     "baseline_answer": b["answer"]})
    n = len(rows)
    gp_wh = sum(r["wh"] for r in rows)
    base_wh = sum(r["baseline_wh"] for r in rows)
    judged = [r for r in rows if r["verdict"] in ("same", "better", "worse")]
    retained = [r for r in rows if r["verdict"] in ("same", "better", "large model")]
    counted = [r for r in rows if r["verdict"] != "unjudged"]
    cats = collections.Counter(r["category"].split("_")[0] for r in rows)  # easy, hard, paraphrase, trap

    routed = [r for r in rows if r["routed"] and r["expected_tier"] in ("small", "large")]
    conf = {f"{e}_{g}": sum(r["expected_tier"] == e and r["routed"] == g for r in routed)
            for e in ("small", "large") for g in ("small", "large")}
    small_routed = [r for r in rows if r["routed"] == "small"]
    para = [r for r in rows if r["category"] == "paraphrase"]
    traps = [r for r in rows if r["category"].startswith("trap")]
    wrong_hits = [r for r in rows if r["cache_hit"] and r["category"] != "paraphrase"]
    lat = {}
    for t in ("cache", "small", "large", "small+large"):
        ls = [r["latency_s"] for r in rows if r["tier"] == t]
        lat[t] = round(statistics.median(ls), 3) if ls else None
    verdicts = collections.Counter(r["verdict"] for r in rows)
    judge_models = sorted({j["judge"] for j in state["judge"].values()})

    return {
        "n": n,
        "run_at": datetime.now().strftime("%d %b %Y, %H:%M"),
        "energy_saved_pct": round(100 * (1 - gp_wh / base_wh), 1) if base_wh else 0,
        "gp_wh": round(gp_wh, 4), "baseline_wh": round(base_wh, 4),
        # Headline figures cover only the answers that were judged (those not from the large model).
        "quality_retained_pct": round(100 * sum(r["verdict"] in ("same", "better") for r in judged) / len(judged), 1)
        if judged else 0,
        "answers_correct_pct": round(100 * sum(r["gp_ok"] for r in judged) / len(judged), 1) if judged else 0,
        "quality_retained_incl_large_pct": round(100 * len(retained) / len(counted), 1) if counted else 0,
        "judged": len(judged), "unjudged": verdicts.get("unjudged", 0), "verdicts": dict(verdicts),
        "trap_count": len(traps), "paraphrase_count": len(para),
        "router_accuracy_pct": round(100 * (conf["small_small"] + conf["large_large"]) / len(routed), 1) if routed else 0,
        "router_n": len(routed), "confusion": conf,
        "escalation_rate_pct": round(100 * sum(r["escalated"] for r in small_routed) / len(small_routed), 1)
        if small_routed else 0,
        "paraphrase_hit_rate_pct": round(100 * sum(r["cache_hit"] for r in para) / len(para), 1) if para else 0,
        "cache_false_hit_rate_pct": round(100 * sum(r["cache_hit"] for r in traps) / len(traps), 1) if traps else 0,
        "unexpected_cache_hits": len(wrong_hits),
        "median_latency_s": lat,
        "measured": sum(r["measured"] for r in rows), "estimated": n - sum(r["measured"] for r in rows),
        "tiers": dict(collections.Counter(r["tier"] for r in rows)),
        "judge_models": judge_models,
        "handcheck": "pending: see results/judge_handcheck.csv",
        "method": (
            f"{n} questions ({cats['easy']} easy, {cats['hard']} hard, {cats['paraphrase']} paraphrases, "
            f"{cats['trap']} cache traps) were each sent straight to the large "
            f"model ({config.LARGE.model}) as the baseline, then through GreenPrompt with an empty cache, in file order. "
            "Local answers are measured as GPU power above idle; cloud answers use published per-prompt estimates. "
            f"Where GreenPrompt did not use the large model, {', '.join(judge_models) or 'a judge model'} compared its "
            "answer with the baseline answer, in random order, as better, same or worse, and said blind whether each answer was correct and adequate. "
            "Quality retained is the share of those judged answers rated same or better. Answers the large model "
            "gave itself were not judged."),
        "limitations": [
            "Questions and labels were drafted with an LLM, then reviewed by hand (5 borderline training labels "
            "kept as they were).",
            "Cloud energy and water are estimates (Google 2025 median prompt, range x0.5 to x2), not measurements; "
            "they are the same for every cloud answer, whatever its length.",
            "Local energy counts the GPU only, not CPU, RAM or cooling.",
            handcheck_note(),
            "Router tuning saw this set: training rows, the unsure band (0.10) and the meaning/length scaling were "
            "chosen while checking it, and a router trained on measured labels was rejected on it, so router "
            "accuracy here is not fully unseen. The router ignores trailing punctuation and case, so casually "
            "typed questions route the same as these.",
            "The router is trained on 250 questions and its accuracy was still rising at that size, so some easy "
            "questions it is unsure about go to the large model (costs energy, not quality).",
        ],
    }, rows


def handcheck_note() -> str:
    """Read from the hand-graded file, so the page never claims more checking than was done."""
    try:
        rows = list(csv.DictReader(open(RES / "judge_handcheck.csv", encoding="utf-8")))
        done = [r for r in rows if r.get("agree", "").strip()]
    except OSError:
        done = []
    if not done:
        return "An LLM judge can be wrong; a 15-question hand check is in progress."
    agree = sum(r["agree"].strip().lower() == "yes" for r in done)
    return (f"An LLM judge can be wrong: in a hand check of {len(done)} of its verdicts we agreed with {agree}. "
            "Where we disagreed, the judge had called a correct but shorter answer worse, so quality retained "
            "is, if anything, conservative.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="rerun pipeline and judge (keeps baseline answers)")
    ap.add_argument("--rejudge", action="store_true", help="rerun only the judge")
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions (smoke test)")
    args = ap.parse_args()
    RES.mkdir(exist_ok=True)
    state = load_state()
    if args.fresh:
        state["pipeline"], state["judge"] = {}, {}
        for p in (CACHE_DB, LOG_DB):
            p.unlink(missing_ok=True)
        save_state(state)
    if args.rejudge:
        state["judge"] = {}
    qs = questions()[: args.limit or None]

    run_baseline(qs, state)
    run_pipeline(qs, state)
    run_judge(qs, state)

    summary, rows = summarise(qs, state)
    show = {k: v for k, v in summary.items() if k not in ("method", "limitations")}
    if args.limit:  # a smoke test must never replace the real results the UI shows
        (RES / "eval_summary_partial.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(show, indent=2), "\n(partial run: written to eval_summary_partial.json only)")
        return
    (RES / "eval_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with open(RES / "eval_rows.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    handcheck = RES / "judge_handcheck.csv"
    if handcheck.exists():  # never overwrite the team's hand grading
        print(f"{handcheck.name} exists, left unchanged (delete it to draw a new sample)")
    else:
        judged = [r for r in rows if r["verdict"] in ("same", "better", "worse")]
        pick = random.Random(15).sample(judged, min(15, len(judged)))
        with open(handcheck, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "prompt", "greenprompt_answer", "baseline_answer", "judge_verdict", "judge_reason",
                        "your_verdict", "agree"])
            for r in pick:
                w.writerow([r["id"], r["prompt"], r["answer"], r["baseline_answer"], r["verdict"], r["judge_reason"],
                            "", ""])
    print(json.dumps(show, indent=2))


if __name__ == "__main__":
    main()
