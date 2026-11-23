from types import SimpleNamespace

from greenprompt import config, models
from greenprompt.config import Endpoint

EP1 = Endpoint("http://a", "m1", "k", "ollama")
EP2 = Endpoint("http://b", "m2", "k", "cloud")


def fake_client(behaviour):
    """behaviour: list of exceptions or reply dicts, consumed per call."""
    calls = []

    def create(model, messages, **kw):
        calls.append(model)
        b = behaviour.pop(0)
        if isinstance(b, Exception):
            raise b
        usage = SimpleNamespace(prompt_tokens=5, completion_tokens=7) if b.get("usage") else None
        msg = SimpleNamespace(content=b["text"])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, calls


def patch(monkeypatch, behaviour, eps=(EP1, EP2)):
    client, calls = fake_client(behaviour)
    monkeypatch.setattr(models, "_down_until", {})
    monkeypatch.setattr(models, "_client", lambda ep: client)
    monkeypatch.setattr(config, "endpoints", lambda tier: list(eps))
    monkeypatch.setattr(models.time, "sleep", lambda s: None)
    return calls


def test_success_with_usage(monkeypatch):
    patch(monkeypatch, [{"text": "120", "usage": True}])
    r = models.chat("small", [])
    assert r.ok and r.text == "120" and r.completion_tokens == 7 and not r.tokens_estimated and not r.fallback


def test_missing_usage_is_estimated(monkeypatch):
    patch(monkeypatch, [{"text": "x" * 40}])
    r = models.chat("small", [])
    assert r.ok and r.tokens_estimated and r.completion_tokens == 10


def test_one_retry_then_success(monkeypatch):
    calls = patch(monkeypatch, [TimeoutError("t"), {"text": "ok", "usage": True}])
    r = models.chat("small", [])
    assert r.ok and calls == ["m1", "m1"] and not r.fallback


def test_falls_back_to_second_endpoint(monkeypatch):
    calls = patch(monkeypatch, [ConnectionError("down"), ConnectionError("down"), {"text": "hi", "usage": True}])
    r = models.chat("small", [])
    assert r.ok and r.model == "m2" and r.fallback and calls == ["m1", "m1", "m2"]


def test_failed_endpoint_is_skipped_during_cooldown(monkeypatch):
    calls = patch(monkeypatch, [ConnectionError("down")] * 2 + [{"text": "a", "usage": True}] * 2)
    models.chat("small", [])
    calls.clear()
    r = models.chat("small", [])
    assert r.ok and r.fallback and calls == ["m2"]


def test_all_fail_never_raises(monkeypatch):
    patch(monkeypatch, [RuntimeError("boom")] * 4)
    r = models.chat("large", [])
    assert not r.ok and "m1" in r.error and "m2" in r.error and r.text == ""


def test_empty_answer_is_not_ok(monkeypatch):
    patch(monkeypatch, [{"text": "  "}, {"text": ""}], eps=(EP1,))
    assert not models.chat("small", []).ok


def test_no_endpoint_configured(monkeypatch):
    patch(monkeypatch, [], eps=())
    r = models.chat("large", [])
    assert not r.ok and "no large model" in r.error
