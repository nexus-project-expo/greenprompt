# Local small model plan (Ollama)

Status: **not yet tested.** Nobody on the team has run a local model before. Do the go/no-go test first, timeboxed to 1 hour, before building anything that depends on it.

## Setup (Windows, Fragan's Acer Nitro 5)

1. Check the GPU: `nvidia-smi` (note the GPU model and VRAM).
2. Install Ollama from https://ollama.com (runs as a background service on port 11434).
3. Pull a ~3B instruct model, quantised Q4 (about 2 GB): `ollama pull qwen2.5:3b` or `ollama pull llama3.2:3b`.
4. Smoke test: `ollama run qwen2.5:3b "Explain normalization in DBMS in 3 lines"`.
5. Python, through the OpenAI-compatible endpoint:
   ```python
   from openai import OpenAI
   c = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
   r = c.chat.completions.create(model="qwen2.5:3b",
         messages=[{"role": "user", "content": "What is 15% of 800?"}])
   print(r.choices[0].message.content, r.usage)
   ```
6. Keep the model warm: Ollama unloads idle models after a few minutes. Set `keep_alive` (request option or `OLLAMA_KEEP_ALIVE` env var) so the first demo question is not slow. Send a warm-up prompt when the app starts.

## Go / no-go checks (`scripts/check_local_model.py` should automate these)

| Check | How | Pass if |
|---|---|---|
| Runs on GPU | `ollama ps` during generation | Processor shows 100% GPU |
| Fast enough | 5 short questions | Median full answer under ~5 s |
| Power readable | NVML / `nvidia-smi --query-gpu=power.draw --format=csv -lms 200` while generating | Real wattage values, clearly above idle |
| Usable answers | 10 easy questions from `data/eval_questions.csv` | Most are acceptable |

Write the results to `results/local_model_check.json` (GPU name, VRAM, model, median latency, idle W, mean W during generation, Wh per answer).

## If it passes

`SMALL_BACKEND=ollama`. The receipt shows **measured** energy and the live power strip. Demo moment: turn Wi-Fi off, ask an easy question, it still answers.

## If any check fails

`SMALL_BACKEND=cloud` with `CLOUD_SMALL_MODEL` set to a small cloud model (e.g. an 8B model on the same provider as the large one). Nothing else in the code changes, because both use the same OpenAI-compatible API. All energy becomes **estimated**. Do not spend more time debugging the local model on build day.

## Things that will come up

- Windows Defender / firewall prompts on first Ollama run: allow it.
- If the model falls back to CPU (`ollama ps` shows CPU), try a smaller model (`qwen2.5:1.5b`, `llama3.2:1b`) before giving up.
- Close games/other GPU apps during the demo so power readings reflect our model (Q17).
- Laptop must be plugged in: on battery, GPU power limits change and numbers shift.
