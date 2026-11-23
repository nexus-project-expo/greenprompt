import time

import pytest

from greenprompt.cache import SemanticCache, names_match

ORIGINAL = "What is normalization in DBMS?"


@pytest.fixture
def cache(tmp_path):
    c = SemanticCache(db_path=tmp_path / "c.db", threshold=0.92, ttl_hours=24)
    c.store(ORIGINAL, "Normalization organises tables to reduce redundancy.", "small-model")
    return c


@pytest.mark.parametrize("prompt", [
    "Explain normalization in DBMS",
    "Can you tell me what normalization means in DBMS?",
    "what is normalisation in dbms",
])
def test_paraphrase_hits(cache, prompt):
    hit = cache.lookup(prompt, has_history=False)
    assert hit and hit.matched_prompt == ORIGINAL and hit.similarity >= 0.92


def test_exact_repeat_hits_and_counts(cache, tmp_path):
    assert cache.lookup(ORIGINAL, False)
    assert cache.lookup(ORIGINAL, False)
    with cache._db() as db:
        assert db.execute("SELECT hits FROM cache").fetchone()[0] == 2


def test_changed_number_misses(tmp_path):
    c = SemanticCache(db_path=tmp_path / "c.db")
    c.store("What is 5% of 800?", "40", "m")
    assert c.lookup("What is 50% of 800?", False) is None
    assert c.lookup("What is 5% of 900?", False) is None
    assert c.lookup("what's 5% of 800?", False)


def test_number_guard_holds_even_at_high_similarity(tmp_path):
    c = SemanticCache(db_path=tmp_path / "c.db", threshold=0.0)  # similarity alone would match anything
    c.store("Convert 5 km to metres", "5000 m", "m")
    assert c.lookup("Convert 6 km to metres", False) is None


def test_changed_entity_misses(tmp_path):
    c = SemanticCache(db_path=tmp_path / "c.db", threshold=0.0)
    c.store("Who is the CEO of Google?", "x", "m")
    assert c.lookup("Who is the CEO of Microsoft?", False) is None
    assert c.lookup("who is the ceo of google", False)


def test_unrelated_misses(cache):
    assert cache.lookup("What is denormalization in DBMS?", False) is None
    assert cache.lookup("What is the capital of France?", False) is None


@pytest.mark.parametrize("prompt", [
    "What's the weather in Udupi today?", "Latest news on ISRO", "Current price of gold",
    "What is the stock price of TCS?", "Who won yesterday?", "IPL score now",
    "What happened on 12/11/2026?", "Events on 25 November", "What's on this week?",
])
def test_time_sensitive_not_cacheable(cache, prompt):
    ok, reason = cache.is_cacheable(prompt, False)
    assert not ok and reason == "time-sensitive"


@pytest.mark.parametrize("prompt", [
    "What about the second method?", "Explain it more simply", "Why is that?",
    "Can you elaborate?", "And how does it compare?", "Rewrite your answer above as bullets",
])
def test_followups_not_cacheable(cache, prompt):
    assert not cache.is_cacheable(prompt, False)[0]


def test_history_not_cacheable_and_never_hits(cache):
    assert cache.is_cacheable(ORIGINAL, has_history=True) == (False, "part of a conversation")
    assert cache.lookup(ORIGINAL, has_history=True) is None


@pytest.mark.parametrize("prompt", [
    "My email is fragan@example.com, write a cover letter", "Call me on +91 98450 12345",
    "Reset my password", "My OTP is 4321 what do I do", "Is my Aadhaar number 123412341234 valid?",
    "What is my account number format",
])
def test_personal_data_not_cacheable(cache, prompt):
    assert cache.is_cacheable(prompt, False) == (False, "looks like personal data")


@pytest.mark.parametrize("prompt", [
    ORIGINAL, "Define photosynthesis", "What is 15% of 800?", "How does TCP differ from UDP?",
    "Write a haiku about rain", "What is the capital of Karnataka?",
])
def test_ordinary_prompts_cacheable(cache, prompt):
    assert cache.is_cacheable(prompt, False) == (True, "cacheable")


def test_ttl_expiry(tmp_path):
    c = SemanticCache(db_path=tmp_path / "c.db", ttl_hours=1)
    c.store(ORIGINAL, "a", "m")
    with c._db() as db:
        db.execute("UPDATE cache SET created_at = ?", (time.time() - 2 * 3600,))
    assert c.lookup(ORIGINAL, False) is None


def test_reported_entry_never_served(cache):
    hit = cache.lookup(ORIGINAL, False)
    cache.report(hit.entry_id)
    assert cache.lookup(ORIGINAL, False) is None


def test_store_skips_empty_and_uncacheable(tmp_path):
    c = SemanticCache(db_path=tmp_path / "c.db")
    c.store("Define entropy", "   ", "m")
    c.store("Weather today?", "sunny", "m")
    with c._db() as db:
        assert db.execute("SELECT COUNT(*) FROM cache").fetchone()[0] == 0


def test_embedding_time_is_recorded(cache):
    cache.lookup("Explain normalization in DBMS", False)
    assert cache.last_embed_s > 0


def test_names_match_ignores_sentence_start():
    assert names_match("Explain normalization in DBMS", "What is normalization in DBMS?")
    assert not names_match("Explain Docker", "Explain Kubernetes")
