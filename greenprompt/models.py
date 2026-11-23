"""OpenAI-compatible chat clients for the small and large tiers. Never raises."""
import time
from dataclasses import dataclass
from typing import Literal

from openai import OpenAI

from greenprompt import config
from greenprompt.config import Endpoint


@dataclass
class ModelResult:
    text: str
    model: str
    tier: Literal["small", "large"]
    backend: Literal["ollama", "cloud"]
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_s: float
    ok: bool
    error: str | None
    tokens_estimated: bool = False
    fallback: bool = False  # True if the tier's first endpoint failed and a backup answered


_clients: dict[Endpoint, OpenAI] = {}
_down_until: dict[Endpoint, float] = {}
COOLDOWN_S = 30  # skip an endpoint this long after it fails; a refused connection costs ~2 s on Windows


def _client(ep: Endpoint) -> OpenAI:
    if ep not in _clients:
        # Retries are done by hand below so the policy is visible: one retry, short backoff.
        _clients[ep] = OpenAI(base_url=ep.base_url, api_key=ep.api_key or "none",
                              timeout=config.REQUEST_TIMEOUT_S, max_retries=0)
    return _clients[ep]


def call(ep: Endpoint, tier: str, messages: list[dict], retries: int = 1) -> ModelResult:
    """One endpoint, with `retries` retries. Returns ok=False instead of raising."""
    extra = {"reasoning_effort": "low"} if ep.model.startswith("openai/gpt-oss") else {}
    t0 = time.perf_counter()
    err = None
    for attempt in range(retries + 1):
        try:
            r = _client(ep).chat.completions.create(model=ep.model, messages=messages, **extra)
            text = (r.choices[0].message.content or "").strip()
            u = r.usage
            pt, ct = (u.prompt_tokens, u.completion_tokens) if u else (None, None)
            est = ct is None
            if est:
                ct = max(1, len(text) // 4)
            return ModelResult(text, ep.model, tier, ep.backend, pt, ct, time.perf_counter() - t0,
                               ok=bool(text), error=None if text else "empty answer", tokens_estimated=est)
        except Exception as e:  # network, auth, timeout, rate limit: all become ok=False
            err = f"{type(e).__name__}: {e}"[:300]
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    return ModelResult("", ep.model, tier, ep.backend, None, None, time.perf_counter() - t0, ok=False, error=err)


def chat(tier: str, messages: list[dict]) -> ModelResult:
    """Try the tier's endpoints in order (e.g. Ollama then cloud small). Never raises."""
    eps = config.endpoints(tier)
    if not eps:
        return ModelResult("", "", tier, "cloud", None, None, 0.0, ok=False, error=f"no {tier} model configured")
    t0 = time.perf_counter()
    now = time.monotonic()
    live = [ep for ep in eps if _down_until.get(ep, 0) <= now] or eps
    errors = []
    for ep in live:
        r = call(ep, tier, messages)
        if r.ok:
            _down_until.pop(ep, None)
            r.fallback = ep != eps[0]
            r.latency_s = time.perf_counter() - t0
            return r
        _down_until[ep] = time.monotonic() + COOLDOWN_S
        errors.append(f"{ep.model}: {r.error}")
    r.error = " | ".join(errors)
    r.latency_s = time.perf_counter() - t0
    return r
