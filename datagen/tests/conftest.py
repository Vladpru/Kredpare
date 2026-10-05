from datetime import date

import pytest

from kredpare_datagen.generate import Dataset, generate_clean
from kredpare_datagen.ground_truth import GroundTruth
from kredpare_datagen.inject import inject

WINDOW_START = date(2026, 8, 10)


@pytest.fixture(scope="session")
def clean() -> Dataset:
    return generate_clean(seed=42, start=WINDOW_START, days=30)


@pytest.fixture(scope="session")
def injected(clean: Dataset) -> tuple[Dataset, list[GroundTruth]]:
    return inject(clean)
