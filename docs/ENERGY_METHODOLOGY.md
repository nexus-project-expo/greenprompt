# Energy, CO2 and water methodology

Rule: every number is tagged **measured** or **estimated**, shows its source, and estimates carry a low/high range. Judges will attack this first (JUDGE_QA.md Q16-Q21), so the method must be simple enough to explain in 30 seconds.

## 1. Local small model (measured)

- Sample GPU power with NVML (`nvidia-ml-py`: `nvmlDeviceGetPowerUsage`, returns milliwatts) every 100-200 ms in a background thread while the model generates. Fallback: poll `nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits`.
- Measure **idle power** once at app start (average of ~3 s with nothing running).
- Energy for the request = sum over samples of `max(0, P_sample - P_idle) * dt`, in joules, then `Wh = J / 3600`. This is *marginal* energy: what the prompt added on top of an idle laptop.
- Also report CPU share if `codecarbon` is easy to wire in; otherwise state "GPU only" on the receipt.
- If power is not readable (`available=False`), fall back to the estimated method below and tag it **estimated**.
- Known limitation to state openly: laptop sensors are coarse, other apps share the GPU (Q17). Close other GPU apps during the demo; mention marginal-over-idle is how we isolate our share.

## 2. Cloud models (estimated)

We cannot measure a provider's data centre. Use per-model figures with a stated source, scaled by output tokens:

`Wh = wh_per_1k_output_tokens[model] * completion_tokens / 1000`, with low/high = x0.5 / x2 unless the source gives its own range.

Put the factors in `data/energy_factors.json`:
```json
{
  "large-model-name": {"wh_per_1k_tokens": null, "low": null, "high": null,
                        "source": "", "notes": ""},
  "fallback_large_median_prompt": {"wh_per_prompt": 0.24, "ml_water_per_prompt": 0.26,
     "source": "Google, Measuring the environmental impact of delivering AI at Google scale, arXiv:2508.15734 (2025): median Gemini Apps text prompt"}
}
```
How to fill it (do this during the build, and record the exact source in the JSON):
- If we use **open-weight models via an API** (e.g. a Llama 8B and a Llama 70B), look up measured inference energy for those exact models on independent benchmarks such as Hugging Face's **AI Energy Score** or the **ML.ENERGY leaderboard**. Check that they cover the exact model and what unit they report before using them. Not yet verified which models they cover.
- If no per-model figure exists, use the Google median prompt figure (0.24 Wh) for the large tier and label it "median prompt, Google 2025". Do not invent per-token numbers.

## 3. Baseline ("what if we had just used the large model")

- For every request, `baseline_wh` = estimated large-model energy for the same prompt (use the large-model factor and the actual answer length, or the 0.24 Wh median).
- `saved_wh = baseline_wh - actual_wh` (actual includes cache lookup + embedding + router + any escalation).
- Dashboard savings % = sum(saved) / sum(baseline).

## 4. Overheads (Q18)

Embedding + classifier + cache lookup run on CPU in milliseconds. Estimate as `CPU_TDP_W * utilisation * seconds` or, simpler and honest, time it and multiply by an assumed CPU package power (state the assumption, e.g. 15 W). Include it in every receipt, including cache hits (so a cache hit is "~0.0001 Wh", not "0").

## 5. CO2 (Q20)

- `g_CO2 = Wh / 1000 * GRID_EF_g_per_kWh`.
- Use India's grid emission factor from the **CEA CO2 Baseline Database for the Indian Power Sector** (latest user guide on cea.nic.in). Look up the current weighted average figure and put it in `.env` with the version number in a comment. Roughly 0.7 kg/kWh in recent versions, **verify before using**.
- Local model: Indian grid factor applies (the laptop is plugged into the Indian grid).
- Cloud model: the data centre location is unknown. Show the same factor but tag "grid location unknown", or use the provider's published per-prompt CO2 if available (Google reports about 0.03 gCO2e for the median Gemini prompt, market-based). Keep energy and CO2 as separate numbers on screen.

## 6. Water (Q21)

- Cloud: 0.26 mL per median prompt (Google 2025), scaled proportionally if we scale energy. Tag **estimated**.
- Local: 0 mL on-site cooling water. Note that water used by power plants is excluded for both, so the comparison is like-for-like on-site water.

## 7. The honest caveat we say out loud (Q16)

A laptop GPU is not automatically greener than a data centre: data centres batch many requests on efficient hardware. That is why we **measure** the local side instead of assuming. Expected result: short answers from a 3B model are cheaper locally; long generations narrow the gap. If our measurement shows local is worse for some class of prompt, the router should send that class to the cloud, and we say so.
