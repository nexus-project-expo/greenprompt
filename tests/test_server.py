import pytest
from fastapi.testclient import TestClient

import server
from greenprompt import energy
from greenprompt.router import RouteDecision


@pytest.fixture
def client(monkeypatch):
    seen = {}

    def handle(prompt, history, accuracy_mode):
        seen.update(prompt=prompt, history=history, accuracy_mode=accuracy_mode)
        r = energy.compute_receipt("small", [], 0.01, 0.2, model="qwen2.5:3b")
        return "an answer", r, RouteDecision("small", 0.1, ["p_hard 0.10"]), {
            "hit": False, "cacheable": True, "cache_reason": "cacheable", "entry_id": 7, "error": None}
    monkeypatch.setattr(server.pipeline, "handle_prompt", handle)
    monkeypatch.setattr(server, "_internet", lambda: True)
    return TestClient(server.app, raise_server_exceptions=False), seen


def test_chat_returns_receipt_and_route(client):
    c, _ = client
    j = c.post("/api/chat", json={"prompt": "What is a firewall?"}).json()
    assert j["answer"] == "an answer" and j["route"]["tier"] == "small" and j["error"] is None
    assert "saved_pct" in j["receipt"] and "entry_id" not in j["cache"]


def test_history_only_sent_for_followups(client):
    c, seen = client
    hist = [{"role": "user", "content": "What is a firewall?"}, {"role": "assistant", "content": "x"}]
    c.post("/api/chat", json={"prompt": "What is a router?", "history": hist})
    assert seen["history"] == []
    c.post("/api/chat", json={"prompt": "Tell me more about it", "history": hist})
    assert seen["history"] == hist


def test_empty_prompt_is_a_json_error(client):
    c, _ = client
    r = c.post("/api/chat", json={"prompt": "   "})
    assert r.status_code == 200 and r.json() == {"error": "empty_prompt"}


def test_unexpected_error_is_json_not_traceback(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(server.pipeline, "parts", lambda: 1 / 0)
    r = c.get("/api/stats")
    assert r.status_code == 200 and r.json() == {"error": "internal"} and "Traceback" not in r.text


def test_status_has_pills(client):
    c, _ = client
    j = c.get("/api/status").json()
    assert {"local_model", "cloud", "grid", "gpu_busy", "warm"} <= j.keys()


def test_bad_body_is_json_error(client):
    c, _ = client
    assert c.post("/api/chat", json={"nope": 1}).json() == {"error": "bad_request"}
    r = c.post("/v1/chat/completions", json={"messages": "x"})
    assert r.status_code == 400 and r.json()["error"]["type"] == "invalid_request_error"


def _sdk(c):
    from openai import OpenAI
    return OpenAI(base_url="http://testserver/v1", api_key="any", http_client=c)


def test_proxy_works_with_openai_sdk(client):
    c, seen = client
    r = _sdk(c).chat.completions.create(model="greenprompt", messages=[
        {"role": "system", "content": "be brief"}, {"role": "user", "content": [{"type": "text", "text": "What is a firewall?"}]}])
    assert r.choices[0].message.content == "an answer" and not seen["accuracy_mode"]
    extra = r.model_extra["greenprompt"]
    assert extra["tier"] == "small" and "wh" in extra
    raw = c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}).text
    assert "matched_prompt" not in raw and "entry_id" not in raw


def test_proxy_passes_system_prompt_so_it_is_not_cached(client):
    c, seen = client
    c.post("/v1/chat/completions", json={"messages": [{"role": "system", "content": "Talk like a pirate."},
                                                      {"role": "user", "content": "What is a firewall?"}]})
    assert seen["history"] == [{"role": "system", "content": "Talk like a pirate."}]


def test_failed_warm_up_shows_local_offline(client, monkeypatch):
    c, _ = client
    monkeypatch.setitem(server.STATUS, "warm", "failed")
    monkeypatch.setattr(server.config, "SMALL_BACKEND", "ollama")
    assert c.get("/api/status").json()["local_model"] == "offline"


def test_proxy_accurate_model_and_streaming(client):
    c, seen = client
    chunks = list(_sdk(c).chat.completions.create(model="greenprompt-accurate", stream=True,
                                                   messages=[{"role": "user", "content": "Prove it"}]))
    assert seen["accuracy_mode"]
    assert "".join(ch.choices[0].delta.content or "" for ch in chunks) == "an answer"
    assert chunks[-1].choices[0].finish_reason == "stop"


def test_proxy_errors_are_openai_shaped(client, monkeypatch):
    c, _ = client
    r = c.post("/v1/chat/completions", json={"messages": [{"role": "assistant", "content": "hi"}]})
    assert r.status_code == 400 and "user message" in r.json()["error"]["message"]

    def down(prompt, history, accuracy_mode):
        r = server.energy.compute_receipt("small", [], 0.0, 0.1)
        return "x", r, None, {"hit": False, "error": "no_model"}
    monkeypatch.setattr(server.pipeline, "handle_prompt", down)
    r = c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503 and r.json()["error"]["type"] == "server_error"


def test_eval_not_run(client, monkeypatch, tmp_path):
    c, _ = client
    monkeypatch.setattr(server.config, "RESULTS_DIR", tmp_path)
    assert c.get("/api/eval").json() == {"error": "not_run"}
