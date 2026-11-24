"""Train the router's logistic regression on data/router_train.csv -> data/router.json.

    python scripts/train_router.py
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from greenprompt import config, embedder, router  # noqa: E402

NEAR_DUP = 0.95  # eval prompts this similar to a training prompt would inflate router accuracy


def read(name: str) -> list[dict]:
    with open(config.DATA_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    train, evalq = read("router_train.csv"), read("eval_questions.csv")
    prompts = [r["prompt"] for r in train]
    y = np.array([r["label"] == "hard" for r in train], dtype=int)
    print(f"{len(train)} training rows: {int((y == 0).sum())} easy, {int(y.sum())} hard; "
          f"{sum(not r['checked'].strip() for r in train)} not yet checked by hand")

    X = router.features(prompts)
    E = embedder.embed([router.normalise(r["prompt"]) for r in evalq])
    sims = E @ X[:, :-1].T  # meaning only, without the length column
    dups = [(evalq[i]["id"], evalq[i]["prompt"], prompts[j], sims[i, j])
            for i, j in enumerate(sims.argmax(1)) if sims[i, j] >= NEAR_DUP]
    if dups:
        print("FAIL: eval prompts overlap the training set:")
        for d in dups:
            print(f"  eval {d[0]} ({d[3]:.2f}): {d[1]!r} ~ {d[2]!r}")
        return 1
    print(f"Disjoint: no eval prompt is within {NEAR_DUP} cosine of a training prompt")

    # Pick regularisation by 5-fold CV on the training set only; the eval set is never used for tuning.
    scores = {}
    for c in (1, 3, 10, 30):
        cv = cross_val_score(LogisticRegression(C=c, class_weight="balanced", max_iter=5000), X, y, cv=5)
        scores[c] = (cv.mean(), cv.std())
    best = max(scores, key=lambda c: scores[c][0])
    print(f"5-fold CV accuracy (classifier alone): {scores[best][0]:.3f} +/- {scores[best][1]:.3f} at C={best}")
    clf = LogisticRegression(C=best, class_weight="balanced", max_iter=5000).fit(X, y)
    router.MODEL_PATH.write_text(json.dumps(
        {"coef": clf.coef_[0].round(6).tolist(), "intercept": round(float(clf.intercept_[0]), 6),
         "embedder": embedder.MODEL_NAME, "rows": len(train)}))
    print("Wrote", router.MODEL_PATH)

    # Routing accuracy on the eval questions that should reach a model (not cache rows).
    r = router.Router()
    rows = [q for q in evalq if q["expected_tier"] in ("small", "large")]
    conf = {(a, b): 0 for a in ("small", "large") for b in ("small", "large")}
    for q in rows:
        conf[(q["expected_tier"], r.decide(q["prompt"], False).tier)] += 1
    acc = (conf[("small", "small")] + conf[("large", "large")]) / len(rows)
    print(f"\nEval routing accuracy (rules + classifier + unsure band): {acc:.1%} on {len(rows)} prompts")
    print(f"  expected small -> small {conf[('small', 'small')]}, -> large {conf[('small', 'large')]} (wasted energy)")
    print(f"  expected large -> large {conf[('large', 'large')]}, -> small {conf[('large', 'small')]} (quality risk)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
