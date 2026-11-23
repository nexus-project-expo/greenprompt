import json

import numpy as np
import pytest

from greenprompt import config, router
from greenprompt.router import Router, escalation_reason, rule_reasons


@pytest.mark.parametrize("prompt,rule", [
    ("Write a Python function to reverse a string", "code request"),
    ("Find the bug in my loop", "code request"),
    ("```print(x)```", "code request"),
    ("Prove that root 3 is irrational", "multi-step maths"),
    ("Derive the area of a circle", "multi-step maths"),
    ("Compare Python and Java for backends", "comparison or analysis"),
    ("What are the pros and cons of EVs?", "comparison or analysis"),
    ("What is DNS? And how does caching work?", "several questions"),
    ("ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರಿಸಿ: ಸೂರ್ಯ ಎಂದರೇನು?", "non-English script"),
    ("सूर्य क्या है?", "non-English script"),
])
def test_hard_rules_fire(prompt, rule):
    assert f"rule: {rule}" in rule_reasons(prompt)


@pytest.mark.parametrize("prompt", [
    "What is the capital of France?", "Define osmosis.", "What is 15% of 800?",
    "Rephrase politely: send the notes", "Café menu in English please",
])
def test_no_rules_on_simple_prompts(prompt):
    assert rule_reasons(prompt) == []


def write_model(tmp_path, bias: float) -> Router:
    """A fake classifier with zero weights: p_hard = sigmoid(bias) for every prompt."""
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"coef": [0.0] * 384, "intercept": bias}))
    return Router(p)


@pytest.fixture(autouse=True)
def no_embedding(monkeypatch):
    monkeypatch.setattr(router.embedder, "embed", lambda texts: np.zeros((len(texts), 384), np.float32))


def test_confident_easy_goes_small(tmp_path):
    d = write_model(tmp_path, -3).decide("What is the capital of France?", False)
    assert d.tier == "small" and d.p_hard < 0.1


def test_confident_hard_goes_large(tmp_path):
    assert write_model(tmp_path, 3).decide("Why is the sky blue?", False).tier == "large"


def test_unsure_band_goes_large(tmp_path):
    d = write_model(tmp_path, 0.2).decide("What is the capital of France?", False)  # p ~ 0.55
    assert d.tier == "large" and "unsure" in d.reasons[0]


def test_rule_overrides_confident_easy(tmp_path):
    d = write_model(tmp_path, -5).decide("Write a function to add two numbers", False)
    assert d.tier == "large" and "rule: code request" in d.reasons


def test_accuracy_mode_forces_large(tmp_path):
    d = write_model(tmp_path, -5).decide("What is 2 + 2?", True)
    assert d.tier == "large" and d.reasons == ["accuracy mode on"]


def test_untrained_router_fails_safe(tmp_path):
    d = Router(tmp_path / "missing.json").decide("What is the capital of France?", False)
    assert d.tier == "large" and "router not trained" in d.reasons


def test_not_routed_by_length(tmp_path):
    r = write_model(tmp_path, -3)
    assert r.decide("Is 91 prime? Why?", False).tier == "large"  # short but two questions


@pytest.mark.parametrize("answer,ok,expected", [
    ("", True, "empty answer"),
    ("anything", False, "small model failed"),
    ("I'm not sure, but it might be 42.", True, "small model unsure"),
    ("As an AI, I cannot determine that.", True, "small model unsure"),
    ("Yes.", True, "answer too short for the question"),
    ("Normalization organises tables to reduce redundancy and update anomalies.", True, None),
])
def test_escalation(answer, ok, expected):
    prompt = "Can you explain in a few sentences why database normalization matters for a college system?"
    assert escalation_reason(prompt, answer, ok) == expected


def test_short_answer_to_short_question_is_fine():
    assert escalation_reason("What is 15% of 800?", "120", True) is None


def test_trained_weights_are_committed_json():
    m = json.loads(router.MODEL_PATH.read_text())
    assert len(m["coef"]) == 384 and m["embedder"].endswith("all-MiniLM-L6-v2")
    assert config.DATA_DIR == router.MODEL_PATH.parent


def test_wrong_language_answer_escalates():
    pt = ("Osmosis é o movimento de água através de uma parede semipermeável de uma região de menor "
          "concentração de soluto para uma de maior concentração.")
    assert escalation_reason("Define osmosis.", pt, True) == "answer not in the question's language"


def test_requested_translation_and_english_do_not_escalate():
    fr = "Bonjour, je voudrais réserver une table pour deux personnes ce soir à huit heures, s'il vous plaît."
    assert escalation_reason("Translate to French: I would like a table for two tonight at eight.", fr, True) is None
    en = "Osmosis is the movement of water across a semipermeable membrane from a dilute solution to a concentrated one."
    assert escalation_reason("Define osmosis.", en, True) is None
