# Demo script (5 minutes + 5 minutes Q&A)

Before the slot: laptop plugged in, other GPU apps closed, cache and dashboard cleared with `python scripts/reset_demo.py --cache` (server stopped; a cached "normalization" answer would skip the live power chart at 1:30), app then started and warmed up, phone hotspot ready as backup internet, backup video open in another window.

| Time | Who | What happens on screen | What we say |
|---|---|---|---|
| 0:00-0:45 | Speaker 1 | Title slide, one chart | Everyone uses huge AI models for tiny tasks. IEA projects data centre electricity roughly doubling by 2030. Google measured ~0.24 Wh and ~0.26 mL water per median prompt. Small per prompt, huge in total, and invisible to users. |
| 0:45-1:30 | Speaker 2 | Architecture diagram: cache -> router -> small/large -> receipt | Sustainability *for* AI. Three parts, one sentence each. |
| 1:30-2:15 | Speaker 3 | Ask "What is normalization in DBMS?" -> small model, receipt, live power strip | It went to the small model. Here's the measured energy vs the large-model estimate. |
| 2:15-2:45 | Speaker 3 | Ask a multi-step reasoning question -> large model, "why this route" | The router knows when it needs the big model. |
| 2:45-3:15 | Speaker 3 | Type "Can you explain normalization in DBMS?" -> cache hit, ~0 Wh, instant (similarity 0.97; free rewordings can fall under the 0.92 threshold). Then ask "What is 50% of 800?" after the 5% starter -> miss | Similar questions reuse answers; different numbers never do. |
| 3:15-3:45 | Speaker 2 | Invite a judge to type any question | (Let it run. Read the receipt aloud.) |
| 3:45-4:30 | Speaker 1 | Dashboard + eval tab | From the 24 Nov run (check the eval tab matches): 55% energy saved vs all-large; 79% of answers not from the large model judged as good as it, 93% judged correct; router 93% accurate with no hard question sent small; 0 of 10 cache traps served wrongly. Read real numbers only. |
| 4:30-5:00 | Speaker 1 | Limitations + next steps slide | Cloud energy is estimated; we measured what we could. The OpenAI-compatible proxy already works with any client; next: campus-wide rollout with per-user cache scoping. |

Optional wow moment if local model works: turn Wi-Fi off before 1:30 and say so.

## If something breaks

- Cloud API down: say "this is exactly the fallback case", show the error handling, continue with cache + local model.
- Laptop issue: play the backup video and narrate it.
- Wrong answer from the small model: show the "report" button and the escalation logic; it's a talking point, not a failure.
