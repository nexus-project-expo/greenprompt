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
