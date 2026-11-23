# Data

**Both CSVs are drafts.** Every label must be checked by a person before we report numbers. When you check a row, put your initials in its `checked` column. `scripts/train_router.py` prints how many rows are still unchecked.

| File | Rows | Columns |
|---|---|---|
| `router_train.csv` | ~200 | `prompt,label` (`easy`/`hard`), `checked` |
| `eval_questions.csv` | 100 | `id,prompt,category,expected_tier,paraphrase_of,checked` |
| `router.json` | | Logistic regression weights written by `scripts/train_router.py` |

Labelling rule: `easy` means a 3B model gives an answer as good as the large model's. If you are unsure, label it `hard`.

The two CSVs must not share prompts, or router accuracy on the eval set means nothing. `train_router.py` checks this.

Eval categories (see `docs/EVALUATION.md`):
- `easy_fact` 25, `easy_rewrite` 15, `hard_reason` 20, `hard_code` 15
- `paraphrase` 15: a rewording of an earlier question; `paraphrase_of` gives the original id, and the expected result is a cache hit
- `trap_number` 5, `trap_entity` 2, `trap_time` 3: look like an earlier question (`paraphrase_of`) but must **miss** the cache
