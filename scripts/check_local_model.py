"""Go/no-go test for the local Ollama small model (docs/LOCAL_MODEL_PLAN.md).

Run with the laptop plugged in and other GPU apps closed:
    python scripts/check_local_model.py
Writes results/local_model_check.json and prints PASS/FAIL per check.
"""
import json
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from greenprompt import config, models  # noqa: E402

SHORT_QS = [
    "What is 15% of 800?",
    "Define photosynthesis in one sentence.",
    "What is the capital of Karnataka?",
    "Convert 5 km to metres.",
    "What does CPU stand for?",
]
# shortcut: fixed easy questions until data/eval_questions.csv exists (phase 3); switch to its easy rows then.
EASY_QS = SHORT_QS + [
    "Explain normalization in DBMS in 3 lines.",
    "Rephrase politely: send me the notes now.",
    "What is the boiling point of water in Celsius?",
    "Give two synonyms for 'happy'.",
    "What is an IP address?",
]


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception as e:
        return f"ERROR {e}"


def read_watts() -> float | None:
    out = run(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"])
    try:
        return float(out.splitlines()[0])
    except (ValueError, IndexError):
        return None


class Sampler:
    """shortcut: minimal nvidia-smi poller for this script; the app uses energy.PowerSampler (phase 4)."""

    def __init__(self):
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()

    def __enter__(self):
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def _loop(self):
        while not self._stop.is_set():
            w = read_watts()
            if w is not None:
                self.samples.append((time.perf_counter(), w))
            time.sleep(0.15)

    def __exit__(self, *a):
        self._stop.set()
        self._t.join()

    def joules_above(self, idle: float) -> float:
        s = self.samples
        return sum(max(0.0, w - idle) * (t2 - t1) for (t1, w), (t2, _) in zip(s, s[1:]))


def ask(q: str):
    return models.call(config.OLLAMA, "small", [{"role": "user", "content": q}], retries=0)


def main() -> int:
    res: dict = {"model": config.OLLAMA.model, "base_url": config.OLLAMA.base_url}
    gpu = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    res["gpu"] = gpu
    print("GPU:", gpu)

    print("Warm-up call (loads the model, can take ~30 s the first time)...")
    w = ask("Say OK.")
    if not w.ok:
        print("FAIL: Ollama did not answer:", w.error)
        print("Is Ollama running and the model pulled?  ollama pull", config.OLLAMA.model)
        res["error"] = w.error
        _write(res)
        return 1

    print("Measuring idle power for 3 s...")
    idle = [x for x in (read_watts() for _ in range(15)) if x is not None and not time.sleep(0.2)]
    res["idle_w"] = round(statistics.mean(idle), 2) if idle else None

    lat, wh, watts = [], [], []
    ps_line = ""
    for q in SHORT_QS:
        with Sampler() as s:
            r = ask(q)
            if not ps_line:
                ps_line = run(["ollama", "ps"]) if shutil.which("ollama") else "ollama CLI not on PATH"
        lat.append(r.latency_s)
        if s.samples and res["idle_w"] is not None:
            wh.append(s.joules_above(res["idle_w"]) / 3600)
            watts += [p for _, p in s.samples]
        print(f"  {r.latency_s:5.2f}s  {q!r} -> {r.text[:70]!r}")

    res["ollama_ps"] = ps_line
    res["median_latency_s"] = round(statistics.median(lat), 2)
    res["mean_w_during_generation"] = round(statistics.mean(watts), 2) if watts else None
    res["wh_per_answer_median"] = round(statistics.median(wh), 5) if wh else None

    print("\nAnswers for the 'usable' check (judge by eye):")
    answers = []
    for q in EASY_QS[len(SHORT_QS):]:
        r = ask(q)
        answers.append({"q": q, "a": r.text})
        print(f"\nQ: {q}\nA: {r.text[:300]}")
    res["sample_answers"] = answers

    checks = {
        "runs_on_gpu": "GPU" in ps_line and "CPU" not in ps_line,
        "fast_enough": res["median_latency_s"] < 5,
        "power_readable": bool(watts) and res["idle_w"] is not None
                          and res["mean_w_during_generation"] > res["idle_w"] + 2,
    }
    res["checks"] = checks
    print("\n== Go / no-go ==")
    print(f"ollama ps: {ps_line}")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"  idle {res['idle_w']} W, generating {res['mean_w_during_generation']} W, "
          f"median {res['median_latency_s']} s, {res['wh_per_answer_median']} Wh/answer")
    print("  CHECK BY EYE  usable answers (above)")
    _write(res)
    return 0 if all(checks.values()) else 1


def _write(res: dict):
    config.RESULTS_DIR.mkdir(exist_ok=True)
    p = config.RESULTS_DIR / "local_model_check.json"
    p.write_text(json.dumps(res, indent=2))
    print("\nWrote", p)


if __name__ == "__main__":
    sys.exit(main())
