# GreenPrompt: team Q&A prep (24–25 Nov 2026)

Everything the team asked and answered while preparing for NEXUS 2026, in one place. Figures come from the final evaluation run (24 Nov, 21:22) unless marked otherwise. For the shortest judge answers, see `docs/JUDGE_QA.md`.

**The numbers to know**

| | |
|---|---|
| Energy saved (100 questions) | **56%** (10.5 Wh vs 24 Wh all-large); **54–58%** across the cloud-estimate range |
| Quality retained | **81%** of 59 answers not from the large model judged same or better (48 same, 11 worse); **93%** judged correct; **89%** counting the large model's own answers |
| Router accuracy | **92.9%** (79/85); **0** hard questions sent small; 6 easy sent large |
| Cache | **0/10** trap questions served wrongly; **67%** of reworded questions reused |
| Median latency | cache **0.017 s**, small model **0.20 s**, large model **1.65 s** |
| Receipts | 49 measured on the GPU, 51 estimated |
| Hand check of the AI judge | agreed on **13 of 15**; on the other 2 the judge was stricter than us |

---

## 1. What it is and why it exists

**What does GreenPrompt do, in one line?**
A layer in front of AI chat models. Each question goes through a cache, then a router that picks the smallest model that can answer, and every answer comes with a receipt of its energy, CO2 and water.

**Why does it exist?**
AI's electricity use is growing fast (IEA: data centres ~415 TWh in 2024 → ~945 TWh by 2030, AI the main driver). Each prompt costs something (Google: 0.24 Wh and 0.26 mL of water per median prompt), but nobody sees it. Most questions don't need a giant model, and many repeat. GreenPrompt **cuts** the waste and **shows** the cost.

**Isn't this just a ChatGPT copy with analytics?**
No. We don't build or train a chat model. We sit **in front of** existing models and decide where each question runs: the cache, a small model on the laptop, or a large cloud model.

**Doesn't ChatGPT already do this?**
Partly. ChatGPT picks between its own fast and thinking models, invisibly, to save its own costs. It never sends your question to a free model on your own hardware, never reuses one user's answer for another, and never shows you the energy cost.

**What's novel?**
- Sustainability *for* AI, rather than AI for sustainability.
- A receipt on every answer, labelled measured (local GPU) or estimated (cloud, with source and range).
- Carbon-first routing across providers and your own hardware.
- A shared cache with safety rules.
- An honest evaluation: a blind judge, a hand check, and an experiment that failed and was rolled back.

Credit prior work openly: routing exists in research (RouteLLM), and semantic caching exists in libraries (GPTCache).

**Who are the customers?**
Organisations that pay for lots of AI usage:
1. **Colleges first:** thousands of students ask the same questions, budgets are tight, and many have sustainability goals.
2. **Companies** with internal assistants or support bots: lower API bills, plus energy figures for sustainability reports.
3. **Ed-tech and app developers.**

Users see the receipts; the organisation pays and saves. Not yet validated with paying customers. The first step is a pilot on our campus.

**Revenue model?** (probably not asked)
Saving energy also saves money: cloud AI is billed per token, while cache hits and local answers are free. It could be sold as a hosted version or a per-institution licence, with an open-source core. Don't quote cost figures; we only measured energy.

---

## 2. How it works

**Architecture**
One Python process: FastAPI (`server.py`) serves the API, the live power stream, an OpenAI-compatible endpoint and the built Next.js UI. The modules:
- `cache.py`: MiniLM embeddings + SQLite
- `router.py`: rules + logistic regression
- `models.py`: one OpenAI-style client for every backend
- `energy.py`: NVML GPU power, the receipt maths, the CEA grid factor
- `store.py`: the SQLite request log behind the Dashboard
- `pipeline.py`: ties them together

The models:
- **Small:** qwen2.5:3b via Ollama on the laptop GPU
- **Large:** gpt-oss-120b on Groq
- **Backups:** gpt-oss-20b (cloud small) and Gemini (large, and the evaluation judge)

**One question, step by step**
1. The prompt arrives (trimmed to 4,000 characters).
2. **Cache check:** is it safe to cache at all? If yes, compare its meaning with saved questions. It's a hit only if similarity ≥ 0.92 *and* the numbers, calculations and names match. A hit takes ~17 ms and ~0 Wh.
3. **Routing:**
   - accuracy mode → large
   - rules (code, proofs, analysis, design, several questions, non-English) → large
   - otherwise the classifier's p_hard: < 0.4 small; 0.4–0.6 unsure, so large; > 0.6 large
4. **Answer:** for local answers, GPU power is sampled 10×/second (the live chart). Fallbacks:
   - local model down → cloud small
   - cloud down → local, with a note
   - everything down → a calm message; the cache still works
5. **Escalation:** if the small answer failed, was empty, said "not sure", was too short, or was in the wrong language, the large model redoes it.
6. **Receipt:** local energy is measured (GPU power above idle × time); cloud energy is estimated (0.24 Wh, 0.26 mL, range 0.12–0.48 Wh). CO2 = energy × 675 g/kWh. "Saved" is the comparison with the all-large baseline.
7. **Save and log:** the answer is cached if safe, and the request is logged as a fingerprint only. On a miss, the chips show the closest cached question and why it wasn't reused.

**How do we switch between models?**
Both are called the same way (the OpenAI API format), just at different addresses: Ollama on `localhost:11434` for small, Groq for large. Switching backends is one line in `.env`.

**Why each technology?**

| Choice | Why |
|---|---|
| FastAPI | One process serving the API, the live stream, the OpenAI endpoint and the UI: less to break |
| Next.js | Live chart and receipt UI; built once to static files, so no Node at demo time |
| Ollama + qwen2.5:3b | Fits the 6 GB GPU, ~0.2 s, works offline, and can be **measured** |
| Groq + gpt-oss-120b | A strong open model, free tier, fast |
| Gemini | Large-model backup, and a judge from a **different model family** (no self-preference) |
| OpenAI-compatible API | Any app switches by changing one URL |
| MiniLM | Meaning vectors in milliseconds on the CPU (keeps GPU readings clean), offline |
| Logistic regression | Decides in microseconds; an LLM deciding "is this hard?" would spend the energy we save |
| numpy + SQLite | A few thousand entries compare in milliseconds; a local file, no database server |
| NVML | Real GPU power 10×/second; it's what makes "measured" possible |
| CEA grid factor | The official Indian government figure, so CO2 is checkable |

**Latency**
Median cache 0.017 s, small 0.20 s, large 1.65 s. The cache and router checks add only milliseconds. After a local answer, the app samples the GPU for ~1 s more so the energy reading is complete; that second isn't counted in the latency shown. For most questions, GreenPrompt is greener *and* faster.

---

## 3. The router

**What classifier do we use?**
scikit-learn **logistic regression**. Input: 384 MiniLM meaning numbers (with trailing "?" stripped, so casual typing routes the same) plus a small length signal. Regularisation C = 0.03, chosen by 5-fold cross-validation (88%). At runtime it's a single numpy dot product on 385 weights stored in `data/router.json`.

**What is p_hard?**
The router's estimated probability that a question needs the large model. Below 0.4 small, 0.4–0.6 unsure (large, to be safe), above 0.6 large. Examples: "What is normalization in DBMS?" 0.16 (small); "capital of France" 0.44 (unsure, large); "prove root 2 is irrational" 0.70 plus a rule (large).

**What are the rules?**
Checked before the classifier; any match goes large:
- **code request:** "class", "bug" and "script" only count alongside programming words
- **multi-step maths**
- **comparison or analysis**
- **design task**
- **several questions:** "??" counts as one
- **non-English script:** π and θ don't count

**Is it routing by length? (spec rule 9)**
Until 24 Nov evening, effectively yes: length dominated the score (+9.4 vs meaning −0.25 on the grade-4 question). We fixed the scaling. Now meaning leads (±3) and length is a nudge (at most +0.4). "Can you please tell me in simple words what photosynthesis is…" is long but goes small; "implement an lru cache" is short but goes large.

**Accuracy?**
92.9% (79/85) on the evaluation set, 0 hard sent small. Cross-validation 88%. Fresh judge-style check: 37/40 easy sent small, 20/20 hard sent large. Honest note: some settings were chosen while checking the evaluation set, and the Evaluation page says so.

**Is 250 training questions too few or too simple?**
Small, and we say so, but:
- we only train a thin layer on top of a language model pre-trained on millions of sentence pairs
- learning curve: 50 → 250 examples took it from 77% → 93%, flattening but still rising
- rules plus the unsure zone mean a mistake costs energy, never quality
- a bigger measured dataset made it *worse*: label quality matters more than count

It's deliberately simple: it decides in milliseconds without spending model energy. The next dataset is anonymised questions from a campus pilot.

**Is it overfitting? ("in 2026, whats 2+3" goes large)**
With 250 examples it learns some spurious patterns. Only 3 training questions even contain a year, so it isn't "years = hard"; phrasings like "in 2026, …" shift the meaning numbers by chance. Designed for it: rules first, unsure goes large, and 0 hard questions sent small. We didn't patch the known misses, because that would itself be overfitting.

**Did we try a better dataset?**
Yes: 135 new questions labelled by experiment (both models answered, and the judge compared).
- "Hard if the small answer was worse" → 82% (the judge calls correct-but-shorter answers worse).
- "Hard if the small answer was wrong" → 88%, but it sent one hard question small.

Both were rejected; the hand-labelled router stays. Data: `data/router_measured_experiment.csv`.

**Escalation in the evaluation?**
0%. None of the small answers tripped the checks, because the router kept hard questions away. The checks catch visible failures, not confident wrong answers, which is why quality was measured separately by the judge.

---

## 4. The cache

**How does it work, and what does it use?**
Our own code in `cache.py`:
- **MiniLM** turns each question into 384 meaning numbers
- **numpy** compares them by cosine similarity
- **SQLite** stores the question, its vector, the answer, the model, the time and a "reported" flag

A hit needs similarity ≥ 0.92 **and** the same numbers, the same calculations (in order, same operators) and the same names.

**Where are cached answers stored?**
In `greenprompt.db` (SQLite) on the laptop. It's never uploaded, and `*.db` files are excluded from git. Entries expire after 24 hours; "Report wrong answer" stops one being served. The "Your questions" list is separate, in each person's browser.

**Prompt caching vs semantic caching? Why wasn't semantic caching done before?**
- **Prompt caching** (OpenAI, Anthropic, Google) reuses the model's work on an *exactly* repeated prompt start. The model still runs and writes a new answer.
- **Semantic caching** reuses the *whole answer* for a question with the same *meaning*. No model runs.

Semantic caching exists in libraries (GPTCache, Redis, LangChain) and in FAQ bots. Mainstream chat apps don't share answers across users because of:
- wrong answers that look right (5% vs 50%)
- personal context (history, memory)
- privacy across users
- stale facts
- low hit rates at global scale

Prompt caching was the risk-free win for providers. We made semantic caching safe for a narrow setting, a campus, with exact checks: 0/10 traps wrong.

**"2+3" didn't reuse "what is 2+3"?**
Fixed. A bare sum was too little text for the embedder (similarity 0.80, needs 0.92). Bare sums are now compared as "What is 2+3?" (0.978, a hit). Words aren't converted: "add two and three" is not turned into digits.

**Why not extract only the operands instead of blocking any extra number?**
A rule can't tell which numbers matter. "In 2026, what is 2+3" (irrelevant) vs "India's GDP in 2020" vs "in 2024" (the whole question). So any number difference means no reuse. A miss costs ~0.006 Wh; a wrong cached answer costs trust.

**Same numbers, different calculation?**
"10/2" vs "2/10" scored 0.974 similar, so calculations must now match in order and operator. Found by a security check and fixed.

**What does "time-sensitive" mean?**
Questions whose answer changes over time (today's weather, live scores, prices, the current PM) are answered but never cached. Words only count in context: "live score" and "current price of gold" yes; "where do polar bears live", "explain credit scores" and "AC current" no (fixed after Pallavi found them).

**Short questions with "it" or "this"?**
"Why is that?" and "explain it simply" have no subject of their own, so they're never cached. One with its own subject ("how does it rain?", "define this term: photosynthesis") is cached.

**On a miss, how do I see why?**
The chips show *closest cached: "…" (numbers differ / similarity 0.80, needs 0.92)*. Another person's question text is shown only if it's nearly identical (≥ 0.75); otherwise just the score.

**Why is "What is 1000000000 + 1?" never cached?**
Deliberately: a 10-digit number can't be told apart from a phone or ID number, so any 9+ digit number is never cached. It's still answered. Privacy beats a cache hit.

---

## 5. Follow-up questions

**Can I ask follow-ups?**
Yes. A message recognised as a follow-up gets the last 3 exchanges sent along. Recognised: "tell me more", "explain it simply", "what about Germany?", "give an example", "in simpler words", "summarise in 3 points", "shorter please", "translate to hindi", "and for germany?" (the last five fixed on 25 Nov). Follow-ups are never cached.

---

## 6. Energy, water and CO2

**Measured vs estimated?**
- **Local answers are measured:** GPU power above idle × time, via NVML. Length counts automatically.
- **Cloud answers are estimated:** a fixed 0.24 Wh and 0.26 mL, labelled est., with a 0.12–0.48 Wh range.
- **Cache hits:** ~0.

**What is the estimate based on?**
Google's 2025 paper *Measuring the environmental impact of delivering AI at Google scale* (arXiv:2508.15734): a median Gemini text prompt uses 0.24 Wh and 0.26 mL of water. It's measured on their real fleet and includes AI chips, host CPU and RAM, idle capacity and cooling. Water is data-centre cooling water, so our receipt says "on-site".

**So it's always 0.24 Wh and 0.26 mL for the large model, whatever the prompt?**
Yes. Groq doesn't publish per-answer energy, and Google published only the per-prompt median, without token counts, so scaling by length would mean inventing a number. It's right on average, not for any single answer: a one-word "yes" is overstated, an essay understated. Our claim is over 100 questions, and it holds at 54–58% across the whole ×0.5–×2 range, because GreenPrompt changes **how many** questions reach the cloud, not what each costs.

**Hugging Face measured gpt-oss-120b at 1.8–8.3 Wh. Why 0.24?**
HF ran one 8-GPU machine answering one question at a time; real services batch hundreds. Using HF's numbers would inflate our savings, so we chose the conservative figure. We use HF only for the 20B/120B **ratio** (~0.25 at every length), which gives gpt-oss-20b ≈ 0.06 Wh.

**Groq uses LPUs, Google uses TPUs. How can we use Google's figure?**
Nobody outside Groq can be exact, because Groq publishes no energy per answer. Google's measured figure is the stand-in, labelled est. with a wide range. If Groq publishes a figure, it's a one-line change in `data/energy_factors.json`.

**What's 675 g/kWh?**
India's official grid emission factor (CEA CO2 Baseline Database v22.0, FY 2025-26): each kWh from India's grid emits ~675 g of CO2. CO2 = energy × 675. Example: 0.24 Wh ≈ 0.162 g.

**Doesn't applying India's factor to US data centres inflate cloud CO2?**
In principle yes; the receipt says "cloud data-centre location unknown". But the headline is energy, which uses no grid factor, and with one factor the CO2 saving equals the energy saving. In the least favourable case for us (cloud on a 200–400 g grid, our laptop on India's 675), the 100-question CO2 saving is still 49–53% instead of 55%, because the energy gap (~40×) dwarfs the grid gap (~2–3×).

**Why does water show 0 mL for local answers?**
The laptop is air-cooled; no water is evaporated on-site. Large-model answers show 0.26 mL, cloud small 0.065 mL, cache hits 0.

**Why is the "all-large baseline" on the Dashboard a straight line?**
Each request's baseline is the same 0.24 Wh estimate, so it grows linearly (e.g. 151 × 0.24 ≈ 36 Wh). The gap to the green line is the saving.

---

## 7. Quality and the AI judge

**Isn't the small model's answer worse?**
Sometimes. That's why we measured it: 81% of non-large answers were judged as good as the large model's, and 93% were judged correct. The 11 "worse" answers were mostly correct but shorter; 3 were wrong, all rewriting tasks.

**How do you know the judge is right?**
We hand-checked 15 of its verdicts and agreed on 13. On the other 2 ("What is normalization in DBMS?", "What is GDP?") the judge called correct but shorter answers worse. So it's strict, and our 81% is conservative. The judge is Gemini, a different model family from the one being judged.

**Why was "What is the weather in Udupi today?" answered "I don't have real-time data"?**
That's the correct answer: no model here has live data, and honest beats invented. It isn't escalated, because the large model can't know either. The point of that demo question is the chip *"not cached: time-sensitive"*.

---

## 8. Privacy and security

**How do we protect user data?**
1. **Most questions never leave the laptop:** 59 of 100 in the evaluation.
2. **Personal data is never cached:** emails, phone numbers, 9+ digit numbers, grouped card or Aadhaar numbers, and words like password, OTP, PAN, CVV, UPI PIN. It fails closed.
3. **No context is shared:** follow-ups, mid-conversation and answer-steering questions are never cached, and the near-miss chip hides unrelated questions.
4. **Minimal local storage:** SQLite on the laptop, the log keeps only a fingerprint (hash) of each question, entries expire in 24 h, the history lives in the browser, and API keys stay on the server.
5. **Honest limits:**
   - the cache is shared by everyone on one server (per-user scoping is next)
   - personal-data detection is pattern-based (a phone number written in words could slip through)
   - cloud questions fall under Groq's policy

**Prompt injection and guardrails?**
The models only produce text: no tools, no actions, no secrets in the prompt, and answers are shown as text, never as HTML. The real risk was **cache poisoning** (planting an answer for others), so prompts that steer the answer ("answer that…", "ignore previous instructions") or contain links are answered but never cached.

---

## 9. Feasibility, scalability and impact

**Feasibility?**
One ordinary laptop (RTX 3060, 6 GB), one process, no Docker. It's a drop-in for any app via the OpenAI API (change one URL), works offline, and runs on free tiers.

**Scalability?**
Today: one laptop answering one question at a time (concurrent requests queue). The path:
- a campus GPU server answering in parallel, with the same API
- a vector index (FAISS) and Postgres for a bigger cache
- a medium model for unsure questions
- retraining on real campus questions
- per-user cache scoping
- providers' real energy figures as they're published
- batch jobs moved to cleaner grid hours

**Impact? (illustration, not a measurement)**
5,000 students × 10 questions a day = 50,000/day, about 12 kWh/day if all went large. At our measured 56%: ~6.7 kWh/day saved, ~2.5 MWh/year, **~1.7 t CO2/year** for one campus. Every saved cloud call is also an API bill avoided.

---

## 10. Ideas for the future (not built)

**Long prompts: how does a 40–60% similarity work?**
Two different numbers:
- **Cache similarity** has no 40–60% band: there's one line at 92%, and 40% or 60% is simply a miss. Long prompts almost never hit, which is correct.
- **0.4–0.6 is the router's p_hard unsure zone**, which goes to the large model.

GreenPrompt doesn't rewrite or compress prompts; it decides where they run.

**Pallavi's four ideas, ranked**
1. **A medium model (7B–14B)** for the questions the router is unsure about. The best next step, low risk. Needs more GPU memory than 6 GB, so a campus server.
2. **Prompt compression.** Real, but most energy goes into *writing* the answer, and trimming can drop important details. Test quality first.
3. **Splitting mixed prompts.** Clever, but the parts often depend on each other; only split clearly independent parts.
4. **Standardising phrasings before caching.** Useful but risky (wrong reuse); only for forms where meaning can't change, keeping the exact-number checks.

**Why not build them today?** Every change resets the testing and the published numbers, and judges score what works (40% of the marks).

---

## 11. The judging rubric (7 min presentation and demo + 3 min Q&A)

| Criterion | Weight | Our answer |
|---|---|---|
| Relevance | 15% | AI's electricity is set to more than double by 2030, and nobody sees the cost of their own questions |
| Innovation | 20% | Carbon-first routing plus an honest receipt; routing and caching exist, our angle is energy and visibility |
| Technical implementation | 20% | Safe semantic cache, trained router, live GPU measurement, fallbacks, 192 tests |
| Functions as intended | 20% | Fully live demo, including with Wi-Fi off |
| Feasibility | 10% | One laptop, OpenAI-compatible (one URL), offline |
| Clarity | 10% | Four slides, a script, a self-explaining receipt |
| Scalability and impact | 5% | A campus server: every repeated question answered once; per-user scoping next |

Every member must be able to explain their own contribution in one line.

---

## 12. Running the demo

**Before the slot**
```
cd C:\Work\greenprompt
.venv\Scripts\activate
python scripts/reset_demo.py --demo        # forget only the demo questions; keeps everything else
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
```
Then:
1. Wait for **Local model: online**.
2. Ask one warm-up question that isn't in the demo, within ~20 minutes of the slot.
3. Click **Clear** under "Your questions" and reload the page.
4. Keep the charger plugged in (on battery the GPU throttles and the busy warning can misfire).
5. If port 8000 is already in use, the app is already running: just open http://localhost:8000.

The **Evaluation tab never resets**; it reads `results/eval_summary.json`. The **Dashboard** keeps all past requests unless you run `reset_demo.py` without `--demo`.

**Demo flow**
1. Easy question ("What is normalization in DBMS?") → small model, measured, live power chart.
2. Hard question (the shop discount) → large model, "rule: multi-step maths", 0.26 mL water.
3. **Wi-Fi off** → "Can you explain normalization in DBMS?" → cache hit in milliseconds, no internet.
4. **Wi-Fi on** → "What is 5% of 800?" then "What is 50% of 800?" → the chip shows *numbers differ*.
5. Judge's turn. If it goes large with "unsure", say: *"it played safe."*
6. **Evaluation tab** → 56 / 81 / 93 / 0, the honest-limit line, and the close. Leave it up for Q&A.

**Sample questions**
- **Easy (local, 0 mL):** "What is photosynthesis?", "Name three rivers in Karnataka", "Who wrote the Jungle Book?", "Explain what a firewall is", "What is 18% of 250?"
- **Hard (large, 0.26 mL):** "Write a Python function to merge two sorted lists", "Compare TCP and UDP for live video streaming", "Prove that the square root of 2 is irrational", "Design a database for a college library"
- **Cache hit:** "What is normalization in DBMS?" → "Can you explain normalization in DBMS?"; "what is 2+3" → "2+3"
- **Cache refuses:** "What is 5% of 800?" → "What is 50% of 800?"; "What is 10/2?" → "What is 2/10?"
- **Never cached:** "What is the weather in Udupi today?", "What is the current price of gold?"
- **Follow-up:** "What is photosynthesis?" → "give an example" → "in simpler words"
- **Avoid on stage:** "What is the capital of France?" and "Where do polar bears live?" (the router is unsure and sends them large)

**Wi-Fi-off test (done 25 Nov, all passed)**
Cloud pill shows offline; easy questions go to the local model (measured); cache hits are instant; hard questions are answered by the small model with a note; the Dashboard and Evaluation still load; with Wi-Fi back on, the cloud returns within ~30 s.

**"GPU busy: readings unreliable"?**
A false alarm on battery: the driver hides the GPU's power limit and the fallback misread utilisation. Fixed on 25 Nov (it now judges by idle watts). Plug in the charger and restart the app.
