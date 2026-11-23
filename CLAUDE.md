# GreenPrompt: context for Claude Code

Read this file first, then the files in `docs/` before writing code.

## What this is

GreenPrompt is our team's entry for the **NEXUS 2026 Student Project Expo** (CSI Student Branch, NMAM Institute of Technology, Nitte).
The exhibition is on **25 November 2026**. We have roughly **one working day** to build it end to end, so a reliable live demo beats feature count.

One line: GreenPrompt sits between a user and AI chat models. Each prompt goes through a semantic cache, then a router that sends it to the smallest model that can handle it, and every answer comes with a receipt showing the energy (Wh), CO2 (g) and water (mL) it used versus sending it straight to a large model.

Team (Team Undervolt): Fragan D'Souza (CSE), Hari Haranath (CSE), Pallavi Pai (AI&DS), all 4th year.

## Docs map

| File | What it holds |
|---|---|
| `docs/PROJECT_BRIEF.md` | Event rules, judging rubric, jury, deadlines, theme, what we submitted |
| `docs/SPEC.md` | Architecture, module contracts, cache and router rules, UI. **The build spec.** |
| `docs/ENERGY_METHODOLOGY.md` | How every number on the receipt is computed and labelled |
| `docs/LOCAL_MODEL_PLAN.md` | Ollama setup, go/no-go test, cloud fallback |
| `docs/BUILD_PLAN.md` | Hour-by-hour plan and who owns what |
| `docs/EVALUATION.md` | The 100-question evaluation we report on stage |
| `docs/JUDGE_QA.md` | 29 likely judge questions, sorted, with our answers |
| `docs/DEMO_SCRIPT.md` | The 5-minute demo flow and backup plan |
| `docs/UI_DESIGN.md` | Visual system, layout and the carbon-receipt design. Follow it for all UI work. |
| `docs/abstract.pdf` | The abstract we submitted. Do not contradict it. |

## Non-negotiable rules

1. **The demo must not fail.** Every external call has a timeout, one retry and a fallback. Nothing in the main flow can raise an unhandled exception to the UI.
2. **Never fake numbers.** Every energy/CO2/water figure is either *measured* or *estimated*, and the UI labels which. Estimates show their source and an uncertainty range. No hard-coded "savings" values anywhere.
3. **Small model backend is swappable by config.** Local Ollama and a cloud small model both use the OpenAI-compatible chat API. Switching between them must be a one-line change in `.env`. See `docs/LOCAL_MODEL_PLAN.md`.
4. **Keep it simple.** One Python process at demo time: FastAPI (`server.py`) calls plain Python modules, serves the API, the OpenAI-compatible `/v1/chat/completions` proxy, and the Next.js UI built as a static export (`web/out`). Node is only needed to build the UI. No microservices, no Docker. (Changed 23 Nov 2026 from Streamlit: Hari knows Next.js, the live power chart needs real-time updates, and the abstract promises a FastAPI proxy.)
5. **Secrets only in `.env`** (gitignored). Commit `.env.example` with empty values. This repo will be pushed to a GitHub organisation.
6. **Modules stay independent** so three people can work in parallel: `cache.py`, `router.py`, `energy.py`, `models.py`, `server.py` (+ `web/`). Agree on the interfaces in `docs/SPEC.md` and don't change them silently.
7. **Abstract consistency.** The submitted abstract says "a small, efficient model" and "a large model". It does not promise a local model, so either backend is fine. It does promise: semantic cache, difficulty router with escalation, carbon receipt and dashboard, CEA grid emission factor for CO2, ~100-question evaluation reporting energy saved and quality retained, and an "accuracy mode" style control is fine to add.

## Tech stack

- Python 3.11+
- FastAPI + uvicorn (API, SSE live power stream, OpenAI-compatible proxy, serves the built UI)
- Next.js (static export) + TypeScript for the UI in `web/`
- `openai` Python SDK pointed at different base URLs (Ollama local, Groq or Gemini OpenAI-compatible endpoints for cloud)
- `sentence-transformers` (`all-MiniLM-L6-v2`, runs fine on CPU) for embeddings
- `numpy` cosine similarity for the cache (FAISS optional; the cache will have at most a few thousand entries)
- `scikit-learn` logistic regression for the router
- `sqlite3` (stdlib) for the request log that feeds the dashboard
- `pynvml` (package `nvidia-ml-py`) or `nvidia-smi` polling for GPU power; `codecarbon` optional
- `pytest` for tests

Verify current model names, free-tier rate limits and base URLs of whichever cloud provider we pick at build time. Do not trust names written from memory.

## Commands (create these)

```
pip install -r requirements.txt
python scripts/check_local_model.py      # go/no-go for Ollama (see LOCAL_MODEL_PLAN.md)
python scripts/train_router.py           # trains data/router.joblib from data/router_train.csv
cd web && npm install && npm run build   # builds the UI into web/out (needs Node, build time only)
uvicorn server:app --port 8000           # the demo: open http://localhost:8000
python scripts/run_eval.py               # writes results/eval_summary.json and eval_rows.csv
pytest -q
```

## Definition of done for the expo

- Ask an easy question: routed to small model, receipt shows Wh/CO2/water, latency, "measured" or "estimated" tag.
- Ask a hard question: routed to large model, UI shows *why* (router probability and any rule that fired).
- Ask the first question again, reworded: cache hit, ~0 Wh, instant.
- Change a number in a cached question ("5%" to "50%"): cache must miss.
- Ask a time-sensitive question ("today's weather"): never served from cache.
- Accuracy-mode toggle forces the large model.
- Dashboard: total requests, cache hit rate, % routed small, Wh and gCO2 saved vs all-large baseline, plus the eval results.
- Killing the internet: cache and local model (if used) still answer; cloud calls fail gracefully with a clear message.
- Backup screen recording of the full demo exists.
