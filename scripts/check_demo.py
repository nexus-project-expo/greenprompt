"""Pre-demo check against the running server: walks the definition-of-done items in CLAUDE.md.
Start the server first (uvicorn server:app --port 8000), then: python scripts/check_demo.py
Uses a unique question per run, so earlier cache entries don't hide a problem."""
import json
import random
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
ok = True


def post(path, body, timeout=150):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=10))


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


def ask(prompt, accuracy=False):
    r = post("/api/chat", {"prompt": prompt, "history": [], "accuracy_mode": accuracy})
    rc = r.get("receipt", {})
    print(f"      -> {rc.get('tier')} {rc.get('wh', 0):.4f} Wh {'measured' if rc.get('measured') else 'est.'} "
          f"{rc.get('latency_s', 0):.2f}s {(r.get('route') or {}).get('reasons', '')}")
    return r


s = get("/api/status")
check("server up and warmed", s["warm"] == "ready", s)
check("local model online", s["local_model"] in ("online", None), s["local_model"])
check("cloud online", s["cloud"] == "online")
check("grid factor set", s["grid"], s["grid"])
if s["gpu_busy"]:
    print("WARN  GPU busy at idle: close games, Steam, video before the demo")

n = random.randint(100, 999)
easy = f"What is {n} divided by 4?"
r = ask(easy)
check("easy question goes to the small model", r["receipt"]["tier"] == "small" and not r["error"])
check("receipt is labelled measured or estimated", "measured" in r["receipt"] and r["receipt"]["sources"])
r = ask(f"what's {n} divided by 4")
check("reworded question is a cache hit", r["cache"]["hit"], r["cache"].get("similarity"))
r = ask(f"What is {n + 1} divided by 4?")
check("changed number misses the cache", not r["cache"]["hit"])
r = ask("What is the weather in Udupi today?")
check("time-sensitive question is never cached", not r["cache"]["cacheable"] and not r["cache"]["hit"])
r = ask("Write a Python function that merges two sorted lists, and explain its time complexity.")
check("hard question goes to the large model", r["receipt"]["tier"] in ("large", "small+large"), r["route"]["reasons"])
r = ask(f"Define the word number {n}.", accuracy=True)
check("accuracy mode forces the large model", r["receipt"]["tier"] == "large")

p = post("/v1/chat/completions", {"model": "greenprompt", "messages": [{"role": "user", "content": easy}]})
check("OpenAI-compatible proxy answers", p["choices"][0]["message"]["content"] and "greenprompt" in p)
st = get("/api/stats")
check("dashboard has requests", st["requests"] > 0, f"{st['requests']} requests, {st['saved_pct']:.0f}% saved")
ev = get("/api/eval")
check("evaluation results present", "error" not in ev, ev.get("run_at", ev))
print("\nALL GOOD" if ok else "\nSOMETHING FAILED, see above")
sys.exit(0 if ok else 1)
