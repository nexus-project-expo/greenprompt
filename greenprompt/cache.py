"""Semantic cache: reuse an earlier answer when a new prompt means the same thing.

Rules are in docs/SPEC.md section 4 (cache.py). Every rule fails safe: when unsure, it is a miss.
"""
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from greenprompt import config, embedder

# Rule 1: follow-ups that only make sense with earlier context.
FOLLOWUP_PHRASES = re.compile(
    r"\b(what about|how about|the (first|second|third|last|other) (one|method|option|step|point|part)?"
    r"|above|previous|earlier|you said|your (answer|reply|last)|same as before|as before|elaborate|tell me more)\b",
    re.I)
PRONOUNS = re.compile(r"\b(it|that|this|they|them|those|these|he|she|its)\b", re.I)
FOLLOWUP_START = re.compile(r"^\s*(and|but|so|also|then|why|how)\b.{0,25}\b(it|that|this|them)\b", re.I)

# Rule 2: answers that go stale.
TIME_WORDS = re.compile(
    r"\b(today|tonight|now|current(ly)?|latest|recent(ly)?|news|weather|forecast|prices?|stocks?|scores?"
    r"|live|trending|yesterday|tomorrow|this (week|month|year)|next (week|month|year)|last (week|night))\b", re.I)
MONTHS = r"(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(t(ember)?)?|oct(ober)?|nov(ember)?|dec(ember)?)"
DATE = re.compile(
    rf"\b\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{2,4}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b"
    rf"|\b\d{{1,2}}(st|nd|rd|th)?\s+{MONTHS}\b|\b{MONTHS}\s+\d{{1,2}}(st|nd|rd|th)?\b", re.I)

# Rule 3: personal data is never cached (or logged raw, see store.py).
PERSONAL = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s-]{8,}\d|\b\d{9,}\b"
    r"|\b(password|passcode|passwd|otp|aadha+r|pan (card|number)|account (number|no)|a/c|cvv|ifsc"
    r"|credit card|debit card|card number|pin code|upi pin|ssn)\b", re.I)

# Rule 3b: a prompt that steers what the answer says (or carries a link) is answered but never cached,
# so nobody can plant an answer in the shared cache for other people to receive.
STEERING = re.compile(
    r"\b(ignore|disregard|forget)\b.{0,30}\b(instructions?|rules|above|previous|prompt)\b"
    r"|\b(system prompt|jailbreak|developer mode|you are now|from now on|pretend (to be|you)|act as|role-?play)\b"
    r"|\b(say|answer|reply|respond|tell (them|users|everyone|people))\b.{0,15}\b(that|with|only)\b"
    r"|\b(start|end|begin|finish) (your|the) (answer|reply|response)\b"
    r"|https?://|www\.|\b[\w-]+\.(com|net|org|io|in|xyz|ru|info|biz)\b", re.I | re.S)

NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9-]*")  # "India's" -> "India", "s"


def followup_reason(prompt: str) -> str | None:
    if FOLLOWUP_PHRASES.search(prompt):
        return "refers to an earlier message"
    if FOLLOWUP_START.search(prompt):
        return "refers to an earlier message"
    # A short prompt built around a pronoun ("why is that?", "explain it simply") has no subject of its own.
    if len(prompt.split()) <= 6 and PRONOUNS.search(prompt):
        return "refers to an earlier message"
    return None


def is_time_sensitive(prompt: str) -> bool:
    return bool(TIME_WORDS.search(prompt) or DATE.search(prompt))


def looks_personal(prompt: str) -> bool:
    return bool(PERSONAL.search(prompt))


def numbers(text: str) -> set[str]:
    return set(NUMBER.findall(text))


def named_tokens(text: str) -> set[str]:
    """Capitalised words that are not sentence-initial, plus acronyms anywhere. Lower-cased."""
    out = set()
    for sentence in re.split(r"(?<=[.?!:;])\s+|\n+", text.strip()):
        for i, m in enumerate(WORD.finditer(sentence)):
            w = m.group()
            if (w.isupper() and len(w) > 1) or (i > 0 and w[0].isupper() and w != "I"):
                out.add(w.lower())
    return out


BARE_MATHS = re.compile(r"^[\d\s.+\-*/x×÷^()%=?]+$")
EXPRESSION = re.compile(r"[\d.()]+(?:[+\-*/x×÷^][\d.()]+)+")


def maths(text: str) -> list[str]:
    """Calculations in the prompt, in order ("10/2" vs "2/10" share numbers but not answers)."""
    flat = re.sub(r"\s+", "", text.lower())
    return [e.replace("x", "*").replace("×", "*").replace("÷", "/") for e in EXPRESSION.findall(flat)]


def as_question(prompt: str) -> str:
    """A bare sum ("2+3") is too short for the embedder to place well (0.80 to "what is 2+3"), so it is
    embedded as the question it means. Only the embedded text changes; the number rule still applies."""
    p = prompt.strip()
    if BARE_MATHS.match(p) and re.search(r"\d", p) and re.search(r"[+\-*/x×÷^%]", p):
        return f"What is {p.rstrip('?= ')}?"
    return prompt


def names_match(a: str, b: str) -> bool:
    """Every named token of each prompt must appear, case-insensitively, in the other one."""
    wa, wb = {w.lower() for w in WORD.findall(a)}, {w.lower() for w in WORD.findall(b)}
    return named_tokens(a) <= wb and named_tokens(b) <= wa


@dataclass
class CacheHit:
    entry_id: int
    answer: str
    model: str
    similarity: float
    matched_prompt: str
    age_hours: float


SCHEMA = """CREATE TABLE IF NOT EXISTS cache (
    id INTEGER PRIMARY KEY, prompt TEXT NOT NULL, embedding BLOB NOT NULL, answer TEXT NOT NULL,
    model TEXT NOT NULL, created_at REAL NOT NULL, hits INTEGER NOT NULL DEFAULT 0,
    flagged INTEGER NOT NULL DEFAULT 0)"""


class SemanticCache:
    def __init__(self, db_path: Path | str | None = None, threshold: float | None = None,
                 ttl_hours: float | None = None):
        self.db_path = str(db_path or config.DB_PATH)
        self.threshold = config.CACHE_SIM_THRESHOLD if threshold is None else threshold
        self.ttl_s = (config.CACHE_TTL_HOURS if ttl_hours is None else ttl_hours) * 3600
        self.last_embed_s = 0.0  # time spent embedding in the last lookup/store, for the receipt (rule 9)
        self._last: tuple[str, np.ndarray] | None = None
        with self._db() as db:
            db.execute(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5)

    def _embed(self, prompt: str) -> np.ndarray:
        if self._last and self._last[0] == prompt:  # store() right after lookup() reuses the vector
            self.last_embed_s = 0.0
            return self._last[1]
        t = time.perf_counter()
        v = embedder.embed([as_question(prompt)])[0]
        self.last_embed_s = time.perf_counter() - t
        self._last = (prompt, v)
        return v

    def is_cacheable(self, prompt: str, has_history: bool) -> tuple[bool, str]:
        if not prompt.strip():
            return False, "empty prompt"
        if has_history:
            return False, "part of a conversation"
        if is_time_sensitive(prompt):
            return False, "time-sensitive"
        if reason := followup_reason(prompt):
            return False, reason
        if looks_personal(prompt):
            return False, "looks like personal data"
        if STEERING.search(prompt):
            return False, "tells the model what to say"
        return True, "cacheable"

    def lookup(self, prompt: str, has_history: bool) -> CacheHit | None:
        self.last_embed_s = 0.0
        self.last_near = None  # on a miss: (closest cached prompt, similarity, why it was not reused)
        if not self.is_cacheable(prompt, has_history)[0]:
            return None
        q = self._embed(prompt)
        cutoff = time.time() - self.ttl_s
        with self._db() as db:
            db.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
            rows = db.execute("SELECT id, prompt, embedding, answer, model, created_at FROM cache "
                              "WHERE flagged = 0").fetchall()
        if not rows:
            return None
        sims = np.stack([np.frombuffer(r[2], dtype=np.float32) for r in rows]) @ q
        q_nums, q_maths = numbers(prompt), maths(prompt)
        top = int(np.argmax(sims))
        top_prompt, top_sim = rows[top][1], float(sims[top])
        if numbers(top_prompt) != q_nums:  # first: this rule blocks reuse at any similarity
            why = "numbers differ"
        elif maths(top_prompt) != q_maths:
            why = "different calculation"
        elif top_sim < self.threshold:
            why = f"similarity {top_sim:.2f}, needs {self.threshold:.2f}"
        else:
            why = "different names"
        self.last_near = (top_prompt, top_sim, why)
        for i in np.argsort(-sims):
            if sims[i] < self.threshold:
                break
            rid, rprompt, _, answer, model, created = rows[i]
            if numbers(rprompt) == q_nums and maths(rprompt) == q_maths and names_match(prompt, rprompt):
                with self._db() as db:
                    db.execute("UPDATE cache SET hits = hits + 1 WHERE id = ?", (rid,))
                return CacheHit(rid, answer, model, float(sims[i]), rprompt, (time.time() - created) / 3600)
        return None

    def store(self, prompt: str, answer: str, model: str) -> None:
        if not answer.strip() or not self.is_cacheable(prompt, False)[0]:
            return
        v = self._embed(prompt)
        with self._db() as db:
            db.execute("INSERT INTO cache (prompt, embedding, answer, model, created_at) VALUES (?, ?, ?, ?, ?)",
                       (prompt, v.astype(np.float32).tobytes(), answer, model, time.time()))

    def report(self, entry_id: int) -> None:
        """'Report wrong answer': the entry is never served again (kept, flagged, for review)."""
        with self._db() as db:
            db.execute("UPDATE cache SET flagged = 1 WHERE id = ?", (entry_id,))

    def clear(self) -> None:
        with self._db() as db:
            db.execute("DELETE FROM cache")
