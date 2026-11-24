"""handle_prompt: cache -> router -> model(s) -> receipt -> log. Never raises."""
import logging
import time

from greenprompt import config, embedder, energy, models
from greenprompt.cache import SemanticCache
from greenprompt.energy import CallEnergy, PowerSampler, Receipt
from greenprompt.router import RouteDecision, Router, escalation_reason
from greenprompt.store import Store

log = logging.getLogger("greenprompt")

SYSTEM = {"role": "system", "content": "You are a helpful assistant. Always reply in the same language as the "
                                      "user's question; if the question is in English, reply in English. "
                                      "Answer clearly and concisely. "
                                      "Write maths in plain text, never LaTeX."}
NO_MODEL_MSG = ("No model could answer right now. Cached answers still work. "
                "Check the internet connection, or that Ollama is running.")

_parts: dict = {}
NEAR_SHOW_FLOOR = 0.75


def parts():
    """Shared cache, router and log, created on first use."""
    if not _parts:
        _parts.update(cache=SemanticCache(), router=Router(), store=Store())
    return _parts["cache"], _parts["router"], _parts["store"]


SENSOR_TAIL_S = 1.0  # keep sampling after a local answer; the power reading lags by about a second


def _ask(tier: str, messages: list[dict]) -> tuple[models.ModelResult, CallEnergy, list]:
    """One model call, with GPU power measured when it runs on the local model."""
    if tier != "small" or config.SMALL_BACKEND != "ollama":  # cloud only: nothing to measure
        r = models.chat(tier, messages)
        return r, CallEnergy(r.model, r.backend, tier, None), [], 0.0
    with PowerSampler() as s:
        r = models.chat(tier, messages)
        local = r.backend == "ollama"
        if local and r.ok:
            s.tail_s = SENSOR_TAIL_S
    joules = s.joules_above_idle if local and r.ok and s.available else None
    return r, CallEnergy(r.model, r.backend, tier, joules), s.trace if local else [], s.tail_s


def handle_prompt(prompt: str, history: list[dict] | None = None, accuracy_mode: bool = False
                  ) -> tuple[str, Receipt, RouteDecision | None, dict]:
    t0 = time.perf_counter()
    try:
        return _handle(prompt, history or [], accuracy_mode, t0)
    except Exception as e:  # last line of defence: the UI must never see a traceback
        log.exception("handle_prompt failed")
        r = energy.compute_receipt("error", [], 0.0, time.perf_counter() - t0)
        return "Something went wrong on our side. Please try again.", r, None, {"error": "internal"}


def _handle(prompt: str, history: list[dict], accuracy_mode: bool, t0: float):
    cache, router, store = parts()
    has_history = bool(history)

    t = time.perf_counter()
    cacheable, why = cache.is_cacheable(prompt, has_history)
    hit = cache.lookup(prompt, has_history) if cacheable else None
    overhead_s = time.perf_counter() - t
    info = {"cacheable": cacheable, "cache_reason": why, "hit": hit is not None}
    if cacheable and not hit and cache.last_near:  # only when lookup ran for THIS prompt; shown so a miss explains itself
        near, sim, reason = cache.last_near
        # Another user's question text is shown only when it is nearly this one, so the chip can't be used to
        # browse what other people asked.
        info["nearest"] = {"prompt": near if sim >= NEAR_SHOW_FLOOR else None, "similarity": sim, "why": reason}

    if hit:
        receipt = energy.compute_receipt("cache", [], overhead_s, time.perf_counter() - t0, model=hit.model)
        info.update(similarity=hit.similarity, matched_prompt=hit.matched_prompt, entry_id=hit.entry_id,
                    age_hours=hit.age_hours)
        store.log_request(prompt, receipt, None, cache_hit=True, ok=True)
        return hit.answer, receipt, None, info

    t = time.perf_counter()
    decision = router.decide(prompt, accuracy_mode)
    overhead_s += time.perf_counter() - t

    messages = [SYSTEM, *history, {"role": "user", "content": prompt}]
    calls, trace, tier = [], [], decision.tier
    tail = [0.0]  # measurement time after answers, excluded from the latency the user sees

    def ask(t: str) -> models.ModelResult:
        res, c, tr, tail_s = _ask(t, messages)
        tail[0] += tail_s
        if res.ok:  # failed calls produce no answer and are not billed as a full prompt
            calls.append(c)
            trace.extend(tr)
        return res

    r = ask(decision.tier)
    if decision.tier == "small":
        if r.fallback:
            decision.reasons.append("local model unavailable, used cloud small model")
        if reason := escalation_reason(prompt, r.text, r.ok):
            decision.reasons.append(f"escalated: {reason}")
            r2 = ask("large")
            if r2.ok:
                r, tier = r2, "small+large"
            elif r.ok:
                decision.reasons.append("large model unavailable, kept small answer")
    elif not r.ok:  # large model down: answer with the small model rather than nothing (Q11)
        decision.reasons.append("large model unavailable, answered by small model")
        r, tier = ask("small"), "small"
    elif r.fallback:
        decision.reasons.append("primary large model unavailable, used backup")

    ok = r.ok
    receipt = energy.compute_receipt(tier, calls, overhead_s, time.perf_counter() - t0 - tail[0],
                                     model=r.model if ok else "", power_trace=trace)
    answer = r.text if ok else NO_MODEL_MSG
    info["error"] = None if ok else "no_model"
    if not ok:
        log.warning("no model answered: %s", r.error)  # provider details stay in the server log
    if ok and cacheable:
        cache.store(prompt, answer, r.model)
    store.log_request(prompt, receipt, decision.p_hard, cache_hit=False, ok=ok)
    return answer, receipt, decision, info


def warm_up() -> dict:
    """Load the embedder, router and local model, then measure idle GPU power. Call once at startup."""
    status = {}
    parts()
    embedder.embed(["warm up"])
    if config.SMALL_BACKEND == "ollama":
        r = models.call(config.OLLAMA, "small", [{"role": "user", "content": "Say OK."}], retries=0, timeout=180)
        status["local_model"] = "online" if r.ok else "offline"
    status["idle_w"] = energy.measure_idle()
    status["idle_util_pct"] = energy.IDLE_UTIL_PCT
    # A busy GPU at idle (a game, a video) makes "power above idle" meaningless; the UI shows this as a warning.
    status["gpu_busy"] = energy.gpu_busy()
    return status
