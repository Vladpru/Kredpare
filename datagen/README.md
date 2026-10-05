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

## CLI

```bash
uv run kredpare-datagen --seed 42 --days 30                 # writes data/generated/
uv run kredpare-datagen --seed 42 --start 2026-08-17 --out /tmp/kp --loans-per-batch 10
uv run kredpare-datagen --clean --out /tmp/kp-clean        # no breaks, empty ground truth
```

The output directory must be empty or not exist yet. It receives:

- one CSV per file, in each party's own format: `seller/`, `cp-quillmont/`, `cp-brackwater/`, `cp-tessaline/`, `cp-orlo/`;
- `manifest.jsonl`: per file `path`, `counterparty_id`, `schema_name`, `batch_id` (upload metadata for files without a batch column), and `sha256`;
- `ground_truth.jsonl`: one record per injected cause, in the format from `docs/domain/break-taxonomy.md`.

The same arguments always produce byte-identical output.

## Tests

`uv run --directory datagen pytest`. The Hypothesis property tests in `tests/test_properties.py` check, across seeds, windows, and batch sizes, that every observable anomaly is in ground truth and nothing else, that clean and injected rows pass schema validation, and that the same seed gives byte-identical files.
