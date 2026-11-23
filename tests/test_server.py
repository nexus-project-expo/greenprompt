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


def test_eval_not_run(client, monkeypatch, tmp_path):
    c, _ = client
    monkeypatch.setattr(server.config, "RESULTS_DIR", tmp_path)
    assert c.get("/api/eval").json() == {"error": "not_run"}
