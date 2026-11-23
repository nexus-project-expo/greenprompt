"""Clear the dashboard's request log before a demo. `--cache` also empties the semantic cache.
Stop the server first, or restart it afterwards."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenprompt.cache import SemanticCache  # noqa: E402
from greenprompt.store import Store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--cache", action="store_true", help="also empty the semantic cache")
args = ap.parse_args()
Store().clear()
print("Request log cleared.")
if args.cache:
    SemanticCache().clear()
    print("Cache cleared.")
