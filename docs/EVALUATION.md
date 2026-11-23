# Evaluation plan (what we report on stage)

The abstract promises "about 100 questions of mixed difficulty, reporting energy saved alongside answer quality retained". This file defines exactly that.

## Dataset: `data/eval_questions.csv`

Columns: `id,prompt,category,expected_tier,paraphrase_of`

| Group | Count | Examples |
|---|---|---|
| Easy factual / definitions | 25 | "What is normalization in DBMS?", "Define photosynthesis" |
| Easy rewriting / formatting | 15 | "Rephrase: ...", "Convert to bullet points: ..." |
| Hard reasoning / multi-step math | 20 | word problems, "prove", "compare X and Y with trade-offs" |
| Hard code | 15 | "write a function that...", "find the bug in..." |
| Cache paraphrases | 15 | rewordings of earlier easy questions (`paraphrase_of` = original id) |
| Cache traps | 10 | same as an earlier question but a number/entity changed, or time-sensitive |

Draft with an LLM, then **a human checks every label**. Keep `router_train.csv` and `eval_questions.csv` disjoint (no overlap, or router accuracy is meaningless).

## Procedure (`scripts/run_eval.py`)

1. **Baseline run:** every prompt straight to the large model. Record answer, tokens, estimated Wh.
2. **GreenPrompt run:** every prompt through the full pipeline (fresh cache, questions in file order so paraphrases come after originals). Record tier, escalation, cache hit, Wh, latency.
3. **Quality judging:** for each prompt where GreenPrompt did not use the large model, ask the large model as judge to compare the GreenPrompt answer with the baseline answer: output `better | same | worse` plus one line of reasoning. Use a fixed judging prompt; randomise answer order to reduce position bias. Hand-check about 15 judgments and report agreement.
4. Respect rate limits: sleep between calls, cache baseline answers to disk so reruns are cheap.

## Metrics written to `results/eval_summary.json`

- `energy_saved_pct` = 1 - sum(GreenPrompt Wh) / sum(baseline Wh)
- `quality_retained_pct` = share of prompts judged `same` or `better`
- `router_accuracy` on non-cache prompts vs `expected_tier`, plus confusion counts (easy->large is wasted energy; hard->small is a quality risk)
- `escalation_rate`
- `cache_hit_rate` on paraphrases and `cache_false_hit_rate` on traps (target 0)
- median latency per tier
- counts of measured vs estimated receipts

Show these as they come out. If quality retained is low, raise the router threshold and say so. Do not tune on the eval set and then report it as unseen; if we tune, say "tuned on this set".
