"""Get ready for a demo.

    python scripts/reset_demo.py --demo    # forget only the demo questions; keep the rest of the cache and the log
    python scripts/reset_demo.py           # clear the dashboard's request log (stop the server first)
    python scripts/reset_demo.py --cache   # clear the log and empty the whole cache (stop the server first)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenprompt.cache import SemanticCache  # noqa: E402
from greenprompt.store import Store  # noqa: E402

# The questions in the pitch script. Anything cached that one of these would hit is removed, so each step
# behaves as in the script: a fresh model answer first, then the cache hit you ask for.
DEMO = [
    "What is normalization in DBMS?",
    "Can you explain normalization in DBMS?",
    "A shop gives 20% off and then 10% off. Is that 30% off? Show the working.",
    "What is 5% of 800?",
    "What is 50% of 800?",
]

ap = argparse.ArgumentParser()
ap.add_argument("--demo", action="store_true", help="remove only the demo questions from the cache")
ap.add_argument("--cache", action="store_true", help="also empty the whole semantic cache")
args = ap.parse_args()

if args.demo:
    cache, removed = SemanticCache(), []
    for q in DEMO:
        while hit := cache.lookup(q, False):
            with cache._db() as db:
                db.execute("DELETE FROM cache WHERE id = ?", (hit.entry_id,))
            removed.append(hit.matched_prompt)
    print(f"Removed {len(removed)} cached answers: {removed}" if removed else "No demo questions were cached.")
    print("The rest of the cache, the dashboard and the evaluation are unchanged.")
    sys.exit(0)

Store().clear()
print("Request log cleared.")
if args.cache:
    SemanticCache().clear()
    print("Cache cleared.")
