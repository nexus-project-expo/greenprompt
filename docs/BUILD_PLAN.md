# Build plan (one day, three people)

Expo: 25 Nov 2026, Project Expo 2:00 PM. Everything below must be done before then, with sleep.

## Owners

| Person | Owns | Files |
|---|---|---|
| Hari | Semantic cache and its rules | `greenprompt/cache.py`, cache tests, cache trap questions |
| Fragan | Model clients, router, energy measurement, local model test | `models.py`, `router.py`, `energy.py`, `scripts/check_local_model.py`, `scripts/train_router.py` |
| Pallavi | Streamlit UI, receipt card, dashboard, slides | `app.py`, `store.py`, presentation |
| All | Pipeline glue, datasets, evaluation, rehearsal | `pipeline.py`, `data/*.csv`, `scripts/run_eval.py` |

Work on separate branches or at least separate files; merge often.

## Timeline

| Block | Task | Exit check |
|---|---|---|
| Hour 0-1 | Repo setup, `.env`, API keys working for large model. **Local model go/no-go** (LOCAL_MODEL_PLAN.md). | Both tiers answer a test prompt from Python |
| Hour 1-2 | Write `router_train.csv` (150-300 rows) and `eval_questions.csv` (100 rows). LLM drafts, humans fix labels. | Files committed, labels checked |
| Hour 2-5 | Parallel: cache (Hari), router + energy (Fragan), UI skeleton with fake data (Pallavi) | Each module has a tiny test passing |
| Hour 5-6 | `pipeline.py` glue, wire UI to real pipeline | Definition-of-done checklist in CLAUDE.md mostly green |
| Hour 6-7 | Run evaluation, fill eval tab | `results/eval_summary.json` exists |
| Hour 7-8 | Fix the worst problems found by eval; tune thresholds; pre-warm cache with 5 demo questions | Demo script runs start to finish 3 times without error |
| Hour 8-9 | Slides (5-minute pitch), record backup demo video | Video saved locally, not only in the cloud |
| Last hour | Rehearse twice with a timer, including Q&A from JUDGE_QA.md | Everyone can explain every module |

## Cut list (drop in this order if behind)

1. Stretch goals (proxy server, deferral queue)
2. CodeCarbon CPU tracking (keep GPU-only, say so)
3. Live power chart (keep the number on the receipt)
4. Eval size 100 -> 50 (say so on the slide)

Never cut: cache number check, accuracy toggle, error handling, honest labels, backup video.
