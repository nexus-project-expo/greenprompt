# Likely judge questions and our answers

Source: 29 questions Pallavi collected. Sorted by what we do about them. Every team member should be able to answer sections A and D.

## A. Built into the prototype (point at the feature)

| # | Question | Our answer / where it lives |
|---|---|---|
| 1 | Two questions look similar but mean different things? | Strict similarity threshold (0.92+, tuned on our paraphrase set) plus exact checks on numbers and named entities. Uncertain means cache miss. `cache.py` rules 4-5. |
| 2 | Same question with a different number (5% vs 50%)? | Numbers are extracted and must match exactly, otherwise miss. Our eval has "cache trap" questions for this; false-hit rate is reported. |
| 3 | "Today's weather" returns yesterday's answer? | Time-sensitive words and dates make a prompt uncacheable. |
| 6 | Follow-ups like "what about the second method?" | Prompts with chat history or follow-up references are never cached. |
| 7 | Cached answer becomes outdated? | Every entry has a TTL (24 h default). |
| 9 | Short question that needs hard reasoning? | We don't route by length. Embedding classifier plus rules for code, multi-step math, comparisons. |
| 10 | Small model is wrong but confident? | Escalation on refusals, uncertainty, empty/very short answers, and an unsure band that defaults to the large model. Honest limit: no system can verify correctness without a stronger model, so we report measured quality retained on 100 questions. |
| 11 | Cloud model unavailable? | Timeout, one retry, then fallback to the other model with a visible note. Cache and local model keep working offline. |
| 14 | User wants the most accurate answer? | Accuracy-mode toggle always uses the large model. |
| 15 | Router makes the wrong decision? | We report router accuracy and the confusion split on a separate 100-question set (disjoint from training, checked by script; we did add training rows after a first look and picked the unsure band while checking it, and we say so). The router ignores punctuation and capitals, so a casually typed question routes the same as a neat one. Errors toward the large model only waste energy; errors toward the small model are caught partly by escalation. |
| 16 | Local GPU uses more electricity than the cloud? | Could be true for long answers. That's why we measure the local side instead of assuming, and route accordingly. See ENERGY_METHODOLOGY section 7. |
| 18 | Energy of cache, embeddings, classifier ignored? | Counted on every receipt, including cache hits. It's tiny compared with an LLM call. |
| 20 | Renewable vs coal electricity? | Energy (Wh) and CO2 are shown separately. CO2 uses India's CEA grid factor; cloud location unknown is labelled. |
| 21 | Water can't be measured? | Labelled estimate from Google's published per-prompt figure. Local on-site cooling water is zero; power-plant water excluded for both. |
| 25 | Slower than ChatGPT? | Latency on every receipt. Cache hits are faster than any model; small model is usually faster than the large one. |
| 26 | Passwords or personal info? | Prompts that look like personal data are never cached or logged raw. |
| 29 | System crashes mid-request? | Timeouts, retries, error handling; the UI never crashes. |

## B. Production concerns, out of scope for the prototype (say how we'd do it)

| # | Question | Answer |
|---|---|---|
| 5 | Same question, different users' personal context? | Scope cache keys per user or per organisation; only share answers to general questions. |
| 8 | Someone poisons the cache? | Only model outputs are stored (users can't write entries directly), a report button removes entries, admins can purge. |
| 12 | Regional languages? | Non-English script currently routes to the large model. Next step: a multilingual small model. |
| 13 | One prompt mixes easy and hard parts? | Routed to large if any part looks hard. Splitting prompts is an open research problem. |
| 17 | Other apps using the GPU? | We measure power above idle and close other GPU apps; in production use per-process attribution. |
| 22 | 100 students at once? | Async queue and concurrency limits; Ollama on one laptop is a demo, a college would run the small model on a shared GPU server. |
| 23 | Local machine runs out of memory? | We use a quantised 3B model (~2 GB); automatic fallback to cloud if loading fails. |
| 24 | Internet goes down? | Cache and local model still work; cloud requests fail with a clear message. |
| 27 | Forcing everything to the small model? | Routing is server-side; users can only force *up* (accuracy mode), never down. |
| 28 | Prompt injection? | Same risk as any chatbot; the router doesn't execute prompt content. Standard input/output filtering in production. |

## C. Hard follow-ups to rehearse

- **"Isn't this just RouteLLM / semantic caching, which already exist?"** Yes, routing and caching exist (RouteLLM, LMSYS 2024; caching libraries like GPTCache). Our contribution is optimising for energy and emissions instead of cost, measuring the local side, and making the cost visible per answer to the user. We don't claim to have invented routing.
- **"Your cloud numbers are guesses."** They're labelled estimates from published sources with ranges. The local numbers are measured. We'd rather show an honest estimate than nothing, which is what users see today.
- **"How much does it actually save?"** Read the number from `results/eval_summary.json`. Never quote a number we didn't measure.
- **"Who would pay for this / deploy it?"** Colleges and companies already paying for AI APIs: fewer large-model calls also means lower API bills, so the sustainability win comes with a cost win.
- **"What did each of you build?"** Each member names their module and one decision they made.

## C2. Pallavi's push-backs (24 Nov): rehearse these, judges will ask the same things

- **"'2+3' didn't reuse 'what is 2+3'. Shouldn't the cache catch rewordings?"** It does for real rewordings ("whats 2+3", "What is 2 + 3?"). A bare sum was too little text for the embedder (similarity 0.80, needs 0.92), so bare sums are now read as "What is 2+3?" before comparing (0.978, a hit). On a miss the app shows the closest cached question and why it was refused.
- **"An extra number (grade 4, 2026) blocks the cache. Why not extract only the operands?"** A rule can't tell which numbers matter: "in 2026, what is 2+3" (irrelevant) vs "India's GDP in 2020" vs "in 2024" (the whole question). So any number difference means no reuse; a miss costs ~0.006 Wh, a wrong cached answer costs trust. Calculations must also match in order and operator: "10/2" never answers "2/10" (they scored 0.974 similar, which is why this rule exists).
- **"Is the router just using question length?" (spec rule 9)** It was, until we caught it: length dominated the score. Now meaning leads (embedding, ±3 on the score) and length is a nudge (at most +0.4). Order of decision: accuracy mode, task-type rules (code, proofs, analysis, design, several questions, non-English), meaning-based classifier, unsure zone 0.4-0.6 goes large, then escalation if the small answer fails.
- **"Isn't the classifier overfitting? 'in 2026, whats 2+3' goes large."** It learns some spurious patterns from only 250 examples. Designed for it: rules first, unsure goes large, so a mistake costs energy, never quality. Evidence: 93% on the 100-question test set with 0 hard questions sent small; on 60 fresh judge-style questions, 37/40 easy went small (3 borderline went large) and 20/20 hard went large. We did not patch the known misses, because that would be overfitting to them. Fix: more real training data.
- **"What is it trained on?"** 250 questions (130 easy, 120 hard), drafted with an AI assistant and labelled by what a 3B model handles well; reviewed by the team. Logistic regression on a 384-number meaning embedding (all-MiniLM-L6-v2) plus length; settings chosen by 5-fold cross-validation (88%). Tested on 100 separate questions; the training script refuses to run if any test question is 95%+ similar to a training one. Why not ask an LLM how hard a question is? That spends the energy we are trying to save.
- **"Is 250 training examples enough?"** We measured it: training on random slices of 50/100/150/200/250 examples and testing on the same 100 separate questions, the full router scores 77% / 83% / 87% / 90% / 93%, and hard questions sent small fall from 1.1 to 0. The big gains come by ~150 examples and the curve is flattening, so 250 is enough for a prototype, but it is still rising: more real, casually phrased questions would keep improving it.
- **"Hugging Face measured gpt-oss-120b at 1.8-8.3 Wh per query. Why 0.24?"** HF ran one 8-GPU machine answering one question at a time; real services batch hundreds, so per-answer energy is far lower. Google's 0.24 Wh is measured on a real production fleet, idle and cooling included. Using HF's numbers would inflate our savings; we chose the conservative figure. We do use HF for the 20B/120B ratio (~0.25 at every length), which is reliable even when the absolute numbers are not.
- **"Cloud energy is always ~0.24 whatever the answer. A 'yes' and an essay cost the same?"** It is Google's median per prompt: right on average, wrong for any single answer, so every cloud receipt says est. and shows 0.12-0.48 Wh. Our claim is over 100 questions, and it holds at 54-58% saved anywhere in that x0.5-x2 range, because GreenPrompt changes how many questions reach the cloud, not what each costs. Scaling by length needs the token count behind Google's median, which isn't published, so we don't invent it. Local answers are measured, so their length counts automatically.
- **"Groq runs on LPUs, Google on TPUs. How can you use Google's figure?"** Groq publishes no energy per answer, so nobody outside Groq can be exact. Google's measured figure is the stand-in, labelled est. with a wide range; if Groq publishes one, it's a one-line change in data/energy_factors.json. Only local answers are exact.
- **"Applying India's grid factor (675 g/kWh) to US data centres doubles cloud CO2 and flatters the local model."** The headline is energy (Wh), which uses no grid factor, and with one factor for everything the CO2 saving equals the energy saving. In the least favourable case for us (cloud on a 200-400 g grid, our laptop on India's 675) the 100-question CO2 saving is still 49-53% instead of 55%, because the energy gap (~40x) is far larger than the grid gap (~2-3x). The receipt already says the cloud location is unknown.

## D. Open limitations we state ourselves (before they ask)

1. Cloud energy is estimated, not measured.
2. Quality is judged by a larger model plus a hand-checked sample, not by humans at scale.
3. The router is trained on a small dataset we labelled ourselves.
