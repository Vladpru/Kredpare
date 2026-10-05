"""Every rendered file maps back, through the lending mappings, to the same canonical rows."""

from kredpare.core.domain import canonical_frame
from kredpare.core.mapping.config import header_hash
from kredpare.core.mapping.normalize import normalize
from kredpare.domains.lending.spec import LENDING
from pydantic import BaseModel

from kredpare_datagen.formats import render_dataset
from kredpare_datagen.generate import Dataset
from kredpare_datagen.ground_truth import GroundTruth


def _source_rows(dataset: Dataset) -> dict[str, list[BaseModel]]:
    rows: dict[str, list[BaseModel]] = {}
    for file in render_dataset(dataset):
        rows[file.path] = []
    for batch in dataset.batches:
        day = batch.settlement_date.isoformat()
        rows[f"seller/funded_{batch.counterparty_id}_{day}.csv"] = list(batch.funded)
        if batch.confirmation is not None:
            rows[f"{batch.counterparty_id}/confirmation_{day}.csv"] = list(batch.confirmation)
    for onboarding in dataset.onboardings:
        rows[f"cp-orlo/onboarding_{onboarding.boarded_date.isoformat()}.csv"].append(onboarding)
    return rows


def test_every_rendered_file_maps_back_to_its_rows(
    injected: tuple[Dataset, list[GroundTruth]],
) -> None:
    dataset, _ = injected
    expected = _source_rows(dataset)

    for file in render_dataset(dataset):
        mapping = LENDING.mapping_for(header_hash(file.content))
        assert mapping is not None, file.path
        assert mapping.schema_name == file.schema_name
        normalized = normalize(mapping, file.content, batch_id=file.batch_id)
        assert normalized.errors == ()
        frame = canonical_frame([values for _, values in normalized.rows])
        validated = LENDING.schema(mapping.schema_name).validate_frame(frame)
        assert validated.errors == ()
        assert list(validated.rows) == expected[file.path], file.path
