import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import run_eval  # noqa: E402
from greenprompt.models import ModelResult  # noqa: E402


class Rng:
    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


def judge_says(monkeypatch, text):
    monkeypatch.setattr(run_eval.models, "call",
                        lambda *a, **k: ModelResult(text, "judge-model", "judge", "cloud", 1, 1, 0.1, True, None))
    monkeypatch.setattr(run_eval.time, "sleep", lambda s: None)


@pytest.mark.parametrize("swap,letter,expected", [
    (False, "A", "better"),  # GreenPrompt answer shown as A
    (False, "B", "worse"),
    (True, "B", "better"),   # swapped: GreenPrompt answer shown as B
    (True, "A", "worse"),
])
def test_verdict_follows_answer_order(monkeypatch, swap, letter, expected):
    judge_says(monkeypatch, f"VERDICT: {letter}\nA_OK: yes\nB_OK: yes\nREASON: fine")
    v = run_eval.judge_one("q", "gp", "base", Rng(0.1 if swap else 0.9))
    assert v["verdict"] == expected and v["gp_ok"]


def test_equal_is_same_and_markdown_is_tolerated(monkeypatch):
    judge_says(monkeypatch, "**VERDICT:** EQUAL\n**A_OK:** yes\n**B_OK:** yes\n**REASON:** both right")
    assert run_eval.judge_one("q", "gp", "base", Rng(0.9))["verdict"] == "same"


def test_correctness_flags_override_a_contradictory_verdict(monkeypatch):
    # GreenPrompt is B (swapped); judge picks B but says B is wrong and A is right.
    judge_says(monkeypatch, "VERDICT: B\nA_OK: yes\nB_OK: no\nREASON: B has a factual error")
    v = run_eval.judge_one("q", "gp", "base", Rng(0.1))
    assert v["verdict"] == "worse" and not v["gp_ok"]


def test_unparseable_judge_returns_none(monkeypatch):
    judge_says(monkeypatch, "I think both are fine.")
    assert run_eval.judge_one("q", "gp", "base", Rng(0.9)) is None
