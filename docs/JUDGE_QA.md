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
| 15 | Router makes the wrong decision? | We report router accuracy and the confusion split on a held-out set. Errors toward the large model only waste energy; errors toward the small model are caught partly by escalation. |
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

## D. Open limitations we state ourselves (before they ask)

1. Cloud energy is estimated, not measured.
2. Quality is judged by a larger model plus a hand-checked sample, not by humans at scale.
3. The router is trained on a small dataset we labelled ourselves.
