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
        r"```|\b(def|class)\s+\w+\s*[(:]|\b(function|return|import|#include|public static|SELECT|console\.log)\b.*[(){};:=]"
        r"|\b(write|implement|refactor|optimi[sz]e|code)\b.{0,50}"
        r"\b(code|function|program|algorithm|regex|regular expression|api|sql)\b"
        r"|\bdebug\b"
        # "class", "bug", "query", "script" are everyday words ("my dance class", "a bug in my garden"): they only
        # count when the question is also about programming.
        r"|^(?=.*\b(?:python|java|javascript|typescript|golang|rust|sql|html|css|react|node|django|flask|code|coding"
        r"|program|programming|software|app|api|function|compiler|error|exception|git|linux|database|loop)\b)"
        r".*?\b(write|implement|fix|find|refactor|optimi[sz]e|solve)\b.{0,50}\b(class|query|bug|script|method|object)\b",
        re.I | re.S)),
    ("multi-step maths", re.compile(
        r"\b(prove|derive|show that|step[- ]by[- ]step|solve for|solve:|integrate|differentiate|integral"
        r"|derivative|probability that|show (the|your) working)\b", re.I)),
    ("comparison or analysis", re.compile(
        r"\b(compare|contrast|assess)\b.*\b(and|vs\.?|versus|with|against)\b"
        r"|\b(analy[sz]e|critique|critically)\b|\b(trade-?offs?|pros and cons)\b", re.I | re.S)),
    ("design task", re.compile(
        r"\b(design|architect)\b.{0,40}\b(system|backend|architecture|schema|database|app|api|service|pipeline)\b",
        re.I | re.S)),
]
NON_LATIN = re.compile(r"[^\x00-ɏͰ-Ͽ -⁯₠-⃏∀-⋿\s\d\W]")  # Greek letters and maths symbols (pi, theta, sum) are not a language
UNSURE = re.compile(
    r"i'?m not sure|i am not sure|i don'?t know|i do not know|as an ai|cannot determine|can'?t determine"
    r"|unable to (answer|determine|help)|i'?m sorry,? but|i cannot help|not enough information", re.I)


def rule_reasons(prompt: str) -> list[str]:
    reasons = [f"rule: {name}" for name, rx in RULES if rx.search(prompt)]
    if len(re.findall(r"[A-Za-z][^?]*\?+", prompt)) >= 2:  # two real questions, not "whats photosynthesis??"
        reasons.append("rule: several questions")
    if NON_LATIN.search(prompt):
        reasons.append("rule: non-English script")
    return reasons


@dataclass
class RouteDecision:
    tier: Literal["small", "large"]
    p_hard: float
    reasons: list[str] = field(default_factory=list)


def normalise(prompt: str) -> str:
    """What the classifier sees, in training and at runtime. The training questions are neatly typed and end
    in "?", so without this a casual "who wrote the happy prince" looked hard just for missing its "?"."""
    return prompt.strip().rstrip("?.! ").strip()


def features(prompts: list[str]) -> np.ndarray:
    """Classifier input: the meaning (MiniLM embedding) plus log word count.
    The embedding is a unit vector, so each of its 384 values is tiny; unscaled, the classifier leaned almost
    entirely on length (a long but easy question looked hard). Scaled up, meaning leads and length only helps."""
    E = embedder.embed([normalise(p) for p in prompts]) * EMBED_SCALE
    L = np.log1p([[len(p.split())] for p in prompts]).astype(np.float32)
    return np.hstack([E, L])


EMBED_SCALE = 20.0


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
        x = features([prompt])[0][: len(w)]  # a 384-weight model (embedding only) still loads
        return 1 / (1 + math.exp(-(float(x @ w) + b)))

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
    if wrong_language(prompt, answer):
        return "answer not in the question's language"
    return None


ENGLISH_WORDS = {"the", "is", "a", "of", "and", "to", "in", "it", "that", "are", "or", "by", "for", "as", "an",
                 "which", "from", "this", "with", "on"}
ASKS_FOR_LANGUAGE = re.compile(r"\b(translat\w*|french|hindi|kannada|tamil|spanish|german|language)\b", re.I)


def wrong_language(prompt: str, answer: str) -> bool:
    """The 3B local model occasionally answers an English question in another language (seen: Portuguese)."""
    if NON_LATIN.search(prompt) or ASKS_FOR_LANGUAGE.search(prompt) or "```" in answer:
        return False
    words = re.findall(r"[a-zA-Z']+", answer.lower())
    return len(words) >= 12 and sum(w in ENGLISH_WORDS for w in words) / len(words) < 0.03
