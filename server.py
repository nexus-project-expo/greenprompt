"""FastAPI app: the JSON API for the UI, the live power stream, and the built Next.js UI (web/out)."""
import asyncio
import dataclasses
import json
import logging
import socket
import threading
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from greenprompt import config, energy, models, pipeline
from greenprompt.cache import followup_reason

log = logging.getLogger("greenprompt")

STATUS: dict = {"warm": "starting"}
_lock = threading.Lock()  # one request at a time, so power measurements never overlap


def _warm():
    try:
        STATUS.update(pipeline.warm_up(), warm="ready")
    except Exception:
        log.exception("warm-up failed")
        STATUS["warm"] = "failed"


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="GreenPrompt", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse({"error": "internal"}, status_code=200)


class ChatIn(BaseModel):
    prompt: str
    history: list[dict] = []
    accuracy_mode: bool = False


@app.post("/api/chat")
def chat(body: ChatIn):
    prompt = body.prompt.strip()[:4000]
    if not prompt:
        return {"error": "empty_prompt"}
    # Only a real follow-up needs the conversation; independent questions stay cacheable.
    history = [m for m in body.history[-6:] if m.get("role") in ("user", "assistant")] if followup_reason(prompt) else []
    with _lock:
        answer, receipt, decision, info = pipeline.handle_prompt(prompt, history, body.accuracy_mode)
    info.pop("entry_id", None)
    return {
        "answer": answer,
        "receipt": {**dataclasses.asdict(receipt), "saved_pct": receipt.saved_pct},
        "route": dataclasses.asdict(decision) if decision else None,
        "cache": info,
        "error": info.get("error"),
    }


class ReportIn(BaseModel):
    prompt: str


@app.post("/api/report")
def report(body: ReportIn):
    cache = pipeline.parts()[0]
    hit = cache.lookup(body.prompt.strip(), False)
    if hit:
        cache.report(hit.entry_id)
    return {"reported": hit is not None}


@app.get("/api/stats")
def stats():
    return pipeline.parts()[2].stats()


@app.get("/api/eval")
def eval_summary():
    path = config.RESULTS_DIR / "eval_summary.json"
    if not path.exists():
        return {"error": "not_run"}
    return json.loads(path.read_text(encoding="utf-8"))


_net = {"t": 0.0, "ok": False}


def _internet() -> bool:
    """Can we reach the large-model host? Checked at most every 10 s."""
    if time.monotonic() - _net["t"] > 10:
        host = urlparse(config.LARGE.base_url).hostname or "api.groq.com"
        try:
            socket.create_connection((host, 443), timeout=1.5).close()
            _net["ok"] = True
        except OSError:
            _net["ok"] = False
        _net["t"] = time.monotonic()
    return _net["ok"]


def _down(ep) -> bool:
    return models._down_until.get(ep, 0) > time.monotonic()


@app.get("/api/status")
def status():
    local = None
    if config.SMALL_BACKEND == "ollama":
        local = "offline" if STATUS.get("local_model") == "offline" or _down(config.OLLAMA) else (
            "starting" if STATUS["warm"] == "starting" else "online")
    return {
        "warm": STATUS["warm"],
        "local_model": local,
        "local_name": config.OLLAMA.model if local else None,
        "cloud": "online" if _internet() and not _down(config.LARGE) else "offline",
        "large_name": config.LARGE.model,
        "grid": energy.FACTORS["grid"]["label"] if config.GRID_EF_G_PER_KWH else None,
        "grid_g_per_kwh": config.GRID_EF_G_PER_KWH,
        "idle_w": STATUS.get("idle_w"),
        "gpu_busy": STATUS.get("gpu_busy", False),
    }


@app.get("/api/power/stream")
async def power_stream(request: Request):
    """Server-sent events, 5 per second: current GPU watts and whether a local answer is being measured."""
    async def events():
        while not await request.is_disconnected():
            s = energy.ACTIVE
            w = s.trace[-1][1] if s and s.trace else await asyncio.to_thread(energy.read_watts)
            yield f"data: {json.dumps({'w': w, 'active': s is not None, 'idle': energy.IDLE_W})}\n\n"
            await asyncio.sleep(0.2)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


UI = config.ROOT / "web" / "out"
if UI.exists():
    app.mount("/", StaticFiles(directory=UI, html=True), name="ui")
else:
    @app.get("/")
    def no_ui():
        return HTMLResponse("<p>UI not built. Run: cd web && npm install && npm run build</p>")
