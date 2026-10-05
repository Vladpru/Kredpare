# datagen

Synthetic data generator, break injector, and ground truth. All data is synthetic. See `docs/domain/counterparties.md` and `docs/domain/break-taxonomy.md`.

A uv workspace member (`kredpare-datagen`, ADR 0007). It imports lending schemas and pricing from `kredpare.domains.lending`, so generated files follow the same rules the backend validates.

| Module | What |
|---|---|
| `calendar` | US bank business days (federal holidays from the `holidays` package) |
| `agreements` | Each buyer's terms by effective date, settlement schedules, cut-off dates |
| `generate` | A clean dataset: seller, buyer, and servicer rows that agree on every loan |
| `inject` | Simple, medium, and hard causes, each with one `GroundTruth` record |
| `formats` | Each party's CSV format (delimiter, dates, money, price, column names and order) |

```python
from datetime import date

from kredpare_datagen.formats import render_dataset
from kredpare_datagen.generate import generate_clean
from kredpare_datagen.inject import inject

dataset, truth = inject(generate_clean(seed=42, start=date(2026, 8, 10), days=30))
files = render_dataset(dataset)
```

The `kredpare-datagen` CLI that writes files and `ground_truth.jsonl` arrives with issue #17.

Tests: `uv run --directory datagen pytest`.
