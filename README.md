# GreenPrompt

Carbon aware routing for everyday AI use. NEXUS 2026 Student Project Expo entry by Team Undervolt (NMAMIT).

GreenPrompt sits between users and AI chat models. Prompts go through a semantic cache, then a router that picks the smallest model able to answer, and every answer comes with a receipt showing its energy, CO2 and water compared with sending it straight to a large model.

Start with `CLAUDE.md` and `docs/`.

## Quick start

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then fill in keys
python scripts/check_local_model.py
python scripts/train_router.py
cd web && npm install && npm run build && cd ..
uvicorn server:app --port 8000   # open http://localhost:8000
```

On demo day, `powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1` does the Ollama, build and server steps in one go. Start it at least five minutes early: Ollama takes about a minute and a half to come up, and the server measures idle GPU power during warm-up.

Before the slot, with the server running:

```
python scripts/check_demo.py          # walks the definition-of-done checks against the live server
python scripts/reset_demo.py --demo   # forget only the demo questions; keeps the rest of the cache and the dashboard
python scripts/reset_demo.py          # stop the server first; clears the dashboard (add --cache to empty the cache)
```

The backup recording is `results/demo_backup.webm` (re-record with `python scripts/record_demo.py`).

## Use it from any OpenAI client

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="unused")
r = client.chat.completions.create(model="greenprompt", messages=[{"role": "user", "content": "Define osmosis."}])
print(r.choices[0].message.content)
print(r.model_extra["greenprompt"])   # tier, Wh, measured or estimated, CO2, water, saved %
```

`model="greenprompt-accurate"` always uses the large model. Streaming works too.

## Evaluation

```
python scripts/run_eval.py            # resumable; --fresh reruns the pipeline, --rejudge reruns the judge
```

It writes `results/eval_summary.json` (shown in the Evaluation tab), `results/eval_rows.csv` with every answer, and `results/judge_handcheck.csv` with 15 judgments for the team to check by hand.

## Tests

```
pytest -q
```
