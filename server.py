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
from fastapi.exceptions import RequestValidationError
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
    if request.url.path.startswith("/v1/"):
        return JSONResponse({"error": {"message": "internal error", "type": "server_error"}}, status_code=500)
    return JSONResponse({"error": "internal"}, status_code=200)


@app.exception_handler(RequestValidationError)
async def on_bad_request(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/v1/"):
        return JSONResponse({"error": {"message": "Malformed request body.", "type": "invalid_request_error"}},
                            status_code=400)
    return JSONResponse({"error": "bad_request"}, status_code=200)


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


# ---------- OpenAI-compatible proxy ----------
# Any OpenAI client works: base_url="http://localhost:8000/v1", any api_key, model "greenprompt"
# ("greenprompt-accurate" forces the large model). Cache internals (matched prompts, ids) are never returned here.

class ChatCompletionIn(BaseModel):
    model: str = "greenprompt"
    messages: list[dict]
    stream: bool = False


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # [{"type": "text", "text": ...}, ...]
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _oai_error(message: str, status: int, kind: str = "invalid_request_error"):
    return JSONResponse({"error": {"message": message, "type": kind}}, status_code=status)


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "greenprompt"}
                                       for m in ("greenprompt", "greenprompt-accurate")]}


@app.post("/v1/chat/completions")
def chat_completions(body: ChatCompletionIn):
    msgs = [{"role": m.get("role"), "content": _text(m.get("content"))} for m in body.messages]
    if not msgs or msgs[-1]["role"] != "user" or not msgs[-1]["content"].strip():
        return _oai_error("The last message must be a non-empty user message.", 400)
    prompt = msgs[-1]["content"].strip()[:4000]
    history = [m for m in msgs[:-1] if m["role"] in ("user", "assistant")][-6:] if followup_reason(prompt) else []
    with _lock:
        answer, r, d, info = pipeline.handle_prompt(prompt, history, body.model.endswith("accurate"))
    if info.get("error"):
        return _oai_error(ERROR_TEXT.get(info["error"], "internal error"), 503, "server_error")
    cid, created = f"chatcmpl-gp{int(time.time() * 1000)}", int(time.time())
    model = r.model or "greenprompt-cache"
    receipt = {"tier": r.tier, "wh": r.wh, "wh_low": r.wh_low, "wh_high": r.wh_high, "measured": r.measured,
               "g_co2": r.g_co2, "ml_water": r.ml_water, "baseline_wh": r.baseline_wh, "saved_pct": r.saved_pct,
               "latency_s": r.latency_s, "cache_hit": info["hit"], "reasons": d.reasons if d else ["cache hit"]}
    if body.stream:
        def events():
            base = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model}
            yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': answer}, 'finish_reason': None}]})}\n\n"
            yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}], 'greenprompt': receipt})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")
    pt = sum(len(m["content"]) for m in msgs) // 4  # shortcut: chars/4 token estimate, fine for a usage field
    ct = len(answer) // 4
    return {
        "id": cid, "object": "chat.completion", "created": created, "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
        "greenprompt": receipt,
    }


ERROR_TEXT = {"no_model": "No model could answer right now. Check the internet connection or Ollama.",
              "internal": "internal error"}


UI = config.ROOT / "web" / "out"
if UI.exists():
    app.mount("/", StaticFiles(directory=UI, html=True), name="ui")
else:
    @app.get("/")
    def no_ui():
        return HTMLResponse("<p>UI not built. Run: cd web && npm install && npm run build</p>")
