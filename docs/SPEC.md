# GreenPrompt build spec

## 1. Request flow

```
user prompt (+ accuracy_mode flag, + has_chat_history flag)
   |
   v
[cache.lookup]  -- hit --> return cached answer, receipt tier="cache"
   | miss / not cacheable
   v
[router.decide] -- accuracy_mode --> large
   | p_hard, rules
   v
small model  or  large model   (models.py, OpenAI-compatible clients)
   |
   +-- small answer looks unreliable? --> escalate to large (log both calls' energy)
   |
   v
[energy.compute_receipt]  (measured for local, estimated for cloud)
   |
   v
[cache.store] if cacheable and answered successfully
   |
   v
[store.log_request] -> sqlite -> dashboard
```

## 2. Suggested layout

```
greenprompt/
  server.py                  # FastAPI: /api/* for the UI, SSE power stream, /v1/chat/completions proxy, serves web/out
  web/                       # Next.js UI (static export): chat, dashboard, eval tabs
  greenprompt/
    __init__.py
    config.py                # loads .env, all thresholds live here
    models.py                # chat(model_tier, messages) -> ModelResult
    cache.py                 # SemanticCache
    router.py                # Router
    energy.py                # power sampling + receipt maths
    store.py                 # sqlite request log
    pipeline.py              # handle_prompt(...) glues everything, never raises
  data/
    router_train.csv         # prompt,label (easy|hard), 150-300 rows
    eval_questions.csv       # id,prompt,category,expected_tier,paraphrase_of
    energy_factors.json      # per-model Wh figures with sources (see ENERGY_METHODOLOGY.md)
  scripts/
    check_local_model.py
    train_router.py
    run_eval.py
  results/                   # eval outputs (gitignore large files, keep summary json)
  tests/
  docs/
  .env.example
  requirements.txt
  README.md
```

## 3. Config (`.env.example`)

```
SMALL_BACKEND=ollama            # ollama | cloud
SMALL_BASE_URL=http://localhost:11434/v1
SMALL_MODEL=qwen2.5:3b
SMALL_API_KEY=ollama            # Ollama ignores it; required by the SDK
LARGE_BASE_URL=                 # e.g. Groq or Gemini OpenAI-compatible endpoint
LARGE_MODEL=
LARGE_API_KEY=
CLOUD_SMALL_MODEL=              # used when SMALL_BACKEND=cloud
REQUEST_TIMEOUT_S=30
CACHE_SIM_THRESHOLD=0.92
CACHE_TTL_HOURS=24
ROUTER_HARD_THRESHOLD=0.5
ROUTER_UNSURE_BAND=0.15         # p_hard within 0.5 +/- band => send to large
GRID_EF_G_PER_KWH=              # from CEA CO2 baseline database, see ENERGY_METHODOLOGY.md
```

## 4. Module contracts

### models.py
```python
@dataclass
class ModelResult:
    text: str
    model: str
    tier: Literal["small", "large"]
    backend: Literal["ollama", "cloud"]
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_s: float
    ok: bool
    error: str | None

def chat(tier: str, messages: list[dict]) -> ModelResult
```
- Uses `openai.OpenAI(base_url=..., api_key=...)` for both tiers.
- Timeout from config, one retry with short backoff, never raises: returns `ok=False` with the error.
- If tokens are missing in the response (some backends), estimate as `len(text)/4` and flag `tokens_estimated=True`.

### cache.py
```python
class SemanticCache:
    def lookup(self, prompt: str, has_history: bool) -> CacheHit | None
    def store(self, prompt: str, answer: str, model: str) -> None
    def is_cacheable(self, prompt: str, has_history: bool) -> tuple[bool, str]  # (ok, reason)
```
Rules (each one answers a judge question, see JUDGE_QA.md):
1. **Not cacheable** if `has_history` is true or the prompt contains follow-up markers ("that", "it", "the second", "above", "previous", "what about") as the main subject. Keep the check simple and conservative. (Q6)
2. **Not cacheable** if it contains time-sensitive words: today, now, current, latest, news, weather, price, stock, score, this week, yesterday, tomorrow, or any explicit date. (Q3, Q7)
3. **Not cacheable** if it looks like personal data: email address, phone number, long digit strings, words like password / OTP / Aadhaar / account number. (Q26)
4. **Similarity:** cosine similarity of MiniLM embeddings >= `CACHE_SIM_THRESHOLD` (start at 0.92, tune on eval paraphrase pairs). (Q1)
5. **Exact-match guards** after similarity passes: the set of numbers (regex `\d+(\.\d+)?%?`) must be identical, and the set of capitalised/named tokens must be identical. Otherwise miss. (Q2)
6. **TTL:** entries expire after `CACHE_TTL_HOURS`. (Q7)
7. Only store answers where the model call succeeded and the answer is non-empty. Keep a `flagged` column and a "report wrong answer" button in the UI that deletes the entry. (Q4, Q8)
8. Store cache in sqlite (prompt, embedding blob, answer, model, created_at, hits, flagged).
9. Count the embedding cost: time the embedding call and add its CPU energy estimate to the receipt (Q18). It will be tiny; showing it is the point.

### router.py
```python
@dataclass
class RouteDecision:
    tier: Literal["small", "large"]
    p_hard: float
    reasons: list[str]      # shown in the UI, e.g. ["rule: code request", "p_hard=0.81"]

class Router:
    def decide(self, prompt: str, accuracy_mode: bool) -> RouteDecision
```
- **Do not route by length alone.** (Q9)
- Features: MiniLM embedding of the prompt (384 dims) -> logistic regression trained on `data/router_train.csv`.
- Hard-rules that force `large` before the classifier: code blocks or "write code/debug", math with multiple steps or "prove/derive", "compare/analyse/evaluate ... and ...", multiple questions in one prompt (Q13), non-English script detected (Q12, simple Unicode-range check), accuracy_mode (Q14).
- Unsure band: if `abs(p_hard - 0.5) < ROUTER_UNSURE_BAND` send to large (fail safe toward quality).
- Escalation after a small answer (Q10): escalate to large if the small answer is empty, very short for a non-trivial prompt, contains refusal/uncertainty phrases ("I'm not sure", "I don't know", "as an AI", "cannot determine"), or the model call failed. Log both calls; the receipt shows the escalation and counts both energies.
- Report router accuracy on the eval set (Q15). Do not claim the router is always right.

### energy.py
See `ENERGY_METHODOLOGY.md` for the maths. Interface:
```python
class PowerSampler:            # context manager, polls GPU power every 100-200 ms in a thread
    def __enter__(self): ...
    def __exit__(self, *a): ...
    joules_above_idle: float
    available: bool             # False if no NVIDIA GPU / power not readable

@dataclass
class Receipt:
    tier: str                    # cache | small | large | small+large (escalated)
    wh: float; wh_low: float; wh_high: float
    g_co2: float
    ml_water: float
    baseline_wh: float           # what an all-large call would have used (estimate)
    saved_wh: float
    measured: bool               # True only for local GPU measurement
    sources: list[str]           # short citations shown on hover
    latency_s: float

def compute_receipt(...) -> Receipt
```

### pipeline.py
`handle_prompt(prompt, history, accuracy_mode) -> (answer, Receipt, RouteDecision | None, cache_info)`. Wraps everything in try/except. If both models fail, return a friendly error message and a zero receipt; never crash the Streamlit app.

### store.py
sqlite table `requests(id, ts, prompt_hash, tier, model, p_hard, escalated, cache_hit, wh, g_co2, ml_water, baseline_wh, latency_s, measured)`. Do not store raw prompts that failed the personal-data check.

## 5. UI (Next.js static export, served by FastAPI)

API used by the UI (all JSON, never 500 to the browser; errors come back as `{"error": "..."}`):
`POST /api/chat {prompt, history, accuracy_mode}`, `GET /api/power/stream` (SSE watts while a request runs),
`POST /api/report {prompt}`, `GET /api/stats`, `GET /api/eval`, `GET /api/status` (backend pills).

- **Chat tab:** text input, accuracy-mode toggle, answer, and a receipt card under each answer:
  `Tier: small (local) | 0.012 Wh measured | 0.006 g CO2 | 0 mL water on-site | vs large: ~0.24 Wh est. | saved 95% | 1.8 s`
  plus "why this route" (reasons list) and "report wrong answer".
- **Live power strip** (if local model and GPU power available): small line chart of watts while generating. This is the demo's visual hook.
- **Dashboard tab:** totals since start, cache hit rate, tier split pie, cumulative Wh/gCO2 saved vs all-large baseline, latency per tier.
- **Evaluation tab:** reads `results/eval_summary.json`: energy saved %, quality retained %, router accuracy, cache false-hit rate, with the method in one paragraph.
- Clean, readable, large font for projector. No clutter.

## 6. Stretch goals (only after the definition of done is met)

1. ~~OpenAI-compatible FastAPI proxy~~ now core: `/v1/chat/completions` lives in `server.py` (the abstract promises it).
2. Carbon-aware deferral queue for batch jobs (show a schedule using an hourly grid-intensity profile; clearly label it a simulation if no live data).
3. Per-user cache scoping (Q5).
