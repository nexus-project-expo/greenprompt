import numpy as np
import pytest

from greenprompt import models, pipeline
from greenprompt.cache import SemanticCache
from greenprompt.models import ModelResult
from greenprompt.router import RouteDecision
from greenprompt.store import Store


class FakeRouter:
    def decide(self, prompt, accuracy_mode):
        hard = accuracy_mode or "prove" in prompt.lower()
        return RouteDecision("large" if hard else "small", 0.9 if hard else 0.1, ["test"])


def result(tier, text="An answer that is long enough to be useful.", ok=True, backend=None, fallback=False):
    backend = backend or ("ollama" if tier == "small" else "cloud")
    model = {"small": "qwen2.5:3b", "large": "openai/gpt-oss-120b"}[tier] if backend == "ollama" or tier == "large" \
        else "openai/gpt-oss-20b"
    return ModelResult(text if ok else "", model, tier, backend, 10, 20, 0.1, ok, None if ok else "down",
                       fallback=fallback)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    # Deterministic fake embedder: identical prompts match, different ones do not.
    def embed(texts):
        out = []
        for t in texts:
            v = np.random.default_rng(abs(hash(t.lower().strip(" ?."))) % 2**32).normal(size=384)
            out.append(v / np.linalg.norm(v))
        return np.asarray(out, np.float32)
    monkeypatch.setattr("greenprompt.cache.embedder.embed", embed)
    store = Store(tmp_path / "log.db")
    monkeypatch.setattr(pipeline, "_parts", {"cache": SemanticCache(tmp_path / "c.db"), "router": FakeRouter(),
                                             "store": store})
    replies = {}
    calls = []

    def chat(tier, messages):
        calls.append(tier)
        out = replies.get(tier, result(tier))
        return out.pop(0) if isinstance(out, list) else out
    monkeypatch.setattr(models, "chat", chat)
    monkeypatch.setattr(pipeline.energy, "IDLE_W", None)  # no GPU in tests
    return replies, calls, store


def test_easy_goes_small_then_hits_cache(setup):
    replies, calls, store = setup
    a1, r1, d1, i1 = pipeline.handle_prompt("What is a firewall?")
    assert r1.tier == "small" and d1.tier == "small" and not i1["hit"]
    a2, r2, d2, i2 = pipeline.handle_prompt("what is a firewall")
    assert i2["hit"] and r2.tier == "cache" and a2 == a1 and d2 is None
    assert calls == ["small"]
    s = store.stats()
    assert s["requests"] == 2 and s["cache_hit_rate"] == 0.5 and s["saved_wh"] > 0


def test_hard_goes_large(setup):
    _, calls, _ = setup
    _, r, d, _ = pipeline.handle_prompt("Prove that root 2 is irrational")
    assert r.tier == "large" and calls == ["large"] and not r.measured


def test_accuracy_mode_forces_large(setup):
    _, calls, _ = setup
    pipeline.handle_prompt("What is a firewall?", accuracy_mode=True)
    assert calls == ["large"]


def test_unsure_small_answer_escalates(setup):
    replies, calls, _ = setup
    replies["small"] = result("small", "I'm not sure about that.")
    answer, r, d, _ = pipeline.handle_prompt("What is a firewall?")
    assert calls == ["small", "large"] and r.tier == "small+large" and r.escalated
    assert any(x.startswith("escalated") for x in d.reasons)
    assert answer == result("large").text


def test_escalation_failure_keeps_small_answer(setup):
    replies, _, _ = setup
    replies["small"] = result("small", "Yes.")
    replies["large"] = result("large", ok=False)
    answer, r, d, _ = pipeline.handle_prompt(
        "Could you please explain in a few sentences why firewalls matter for a small college network today?")
    assert answer == "Yes." and r.tier == "small"
    assert "large model unavailable, kept small answer" in d.reasons


def test_large_down_falls_back_to_small(setup):
    replies, calls, _ = setup
    replies["large"] = result("large", ok=False)
    answer, r, d, _ = pipeline.handle_prompt("Prove that root 2 is irrational")
    assert calls == ["large", "small"] and r.tier == "small" and answer == result("small").text
    assert any("large model unavailable" in x for x in d.reasons)


def test_everything_down_gives_friendly_message(setup):
    replies, _, store = setup
    replies["small"] = result("small", ok=False)
    replies["large"] = result("large", ok=False)
    answer, r, d, info = pipeline.handle_prompt("What is a firewall?")
    assert answer == pipeline.NO_MODEL_MSG and info["error"] == "no_model" and r.wh < 0.001
    assert store.stats()["requests"] == 0  # failed requests do not count in the dashboard
    # and nothing was cached
    replies.clear()
    _, r2, _, i2 = pipeline.handle_prompt("What is a firewall?")
    assert not i2["hit"]


def test_unexpected_exception_never_escapes(setup, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(pipeline, "_handle", boom)
    answer, r, d, info = pipeline.handle_prompt("anything")
    assert "went wrong" in answer and info["error"] == "internal" and d is None
    assert "disk on fire" in caplog.text  # details are logged, not returned


def test_followup_with_history_is_not_cached(setup):
    _, calls, _ = setup
    hist = [{"role": "user", "content": "What is a firewall?"}, {"role": "assistant", "content": "x"}]
    pipeline.handle_prompt("What is a firewall?")
    _, _, _, info = pipeline.handle_prompt("What is a firewall?", history=hist)
    assert not info["hit"] and info["cache_reason"] == "part of a conversation" and calls == ["small", "small"]


def test_time_sensitive_never_cached(setup):
    _, calls, _ = setup
    pipeline.handle_prompt("What is the weather today?")
    _, _, _, info = pipeline.handle_prompt("What is the weather today?")
    assert not info["hit"] and calls == ["small", "small"]


def test_cloud_small_fallback_is_noted_and_estimated(setup):
    replies, _, _ = setup
    replies["small"] = result("small", backend="cloud", fallback=True)
    _, r, d, _ = pipeline.handle_prompt("What is a firewall?")
    assert not r.measured and "local model unavailable, used cloud small model" in d.reasons


def test_store_never_keeps_raw_prompt(setup):
    _, _, store = setup
    pipeline.handle_prompt("My OTP is 4821, what now?")
    with store._db() as db:
        dump = " ".join(str(v) for row in db.execute("SELECT * FROM requests") for v in row)
    assert "4821" not in dump and "OTP" not in dump
