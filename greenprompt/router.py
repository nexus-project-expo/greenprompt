"""Difficulty router: send each prompt to the smallest model that can handle it.

Hard rules first (they force the large model), then a logistic regression on the MiniLM
embedding. Prompts the classifier is unsure about go to the large model.
"""
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from greenprompt import config, embedder

MODEL_PATH = config.DATA_DIR / "router.json"  # logistic regression weights, written by scripts/train_router.py

RULES = [
    ("code request", re.compile(
        r"```|\b(def|class|function|return|import|#include|public static|SELECT|console\.log)\b.*[(){};:=]"
        r"|\b(write|implement|debug|fix|refactor|optimi[sz]e|code)\b.{0,50}"
        r"\b(code|function|program|script|class|query|bug|algorithm|regex|regular expression|api)\b"
        r"|\b(find|fix) the bug\b|\bdebug\b", re.I | re.S)),
    ("multi-step maths", re.compile(
        r"\b(prove|derive|show that|step[- ]by[- ]step|solve for|solve:|integrate|differentiate|integral"
        r"|derivative|probability that|show (the|your) working)\b", re.I)),
    ("comparison or analysis", re.compile(
        r"\b(compare|contrast|analy[sz]e|evaluate|assess|critique)\b.*\b(and|vs\.?|versus|with|against)\b"
        r"|\b(trade-?offs?|pros and cons)\b", re.I | re.S)),
]
NON_LATIN = re.compile(r"[^\x00-ɏ -⁯₠-⃏\s\d\W]")
UNSURE = re.compile(
    r"i'?m not sure|i am not sure|i don'?t know|i do not know|as an ai|cannot determine|can'?t determine"
    r"|unable to (answer|determine|help)|i'?m sorry,? but|i cannot help|not enough information", re.I)


def rule_reasons(prompt: str) -> list[str]:
    reasons = [f"rule: {name}" for name, rx in RULES if rx.search(prompt)]
    if prompt.count("?") >= 2:
        reasons.append("rule: several questions")
    if NON_LATIN.search(prompt):
        reasons.append("rule: non-English script")
    return reasons


@dataclass
class RouteDecision:
    tier: Literal["small", "large"]
    p_hard: float
    reasons: list[str] = field(default_factory=list)


class Router:
    def __init__(self, model_path: Path | str | None = None):
        path = Path(model_path or MODEL_PATH)
        try:
            m = json.loads(path.read_text())
            self.clf = (np.asarray(m["coef"], dtype=np.float32), float(m["intercept"]))
        except Exception:
            self.clf = None  # untrained: everything not caught by a rule falls in the unsure band -> large

    def p_hard(self, prompt: str) -> float:
        if self.clf is None:
            return 0.5
        w, b = self.clf
        return 1 / (1 + math.exp(-(float(embedder.embed([prompt])[0] @ w) + b)))

    def decide(self, prompt: str, accuracy_mode: bool) -> RouteDecision:
        if accuracy_mode:
            return RouteDecision("large", 1.0, ["accuracy mode on"])
        p = self.p_hard(prompt)
        reasons = rule_reasons(prompt)
        if self.clf is None:
            reasons.append("router not trained")
        if reasons:
            return RouteDecision("large", p, reasons + [f"p_hard {p:.2f}"])
        if abs(p - config.ROUTER_HARD_THRESHOLD) < config.ROUTER_UNSURE_BAND:
            return RouteDecision("large", p, [f"p_hard {p:.2f}, unsure so large"])
        tier = "large" if p >= config.ROUTER_HARD_THRESHOLD else "small"
        return RouteDecision(tier, p, [f"p_hard {p:.2f}", "no rules fired"] if tier == "small" else [f"p_hard {p:.2f}"])


def escalation_reason(prompt: str, answer: str, ok: bool) -> str | None:
    """Why a small-model answer should be redone by the large model, or None if it looks usable."""
    if not ok:
        return "small model failed"
    if not answer.strip():
        return "empty answer"
    if UNSURE.search(answer[:400]):
        return "small model unsure"
    if len(prompt.split()) >= 12 and len(answer.split()) < 4:
        return "answer too short for the question"
    return None
