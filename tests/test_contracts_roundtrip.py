"""Contracts import + fixture round-trip — task P1-BE-17.

A harness-level smoke test: every top-level contract imports from the package
root, and its canonical example survives ``dict``/JSON round-trips unchanged.
This is the test the ``pytest``/``--cov=backend`` wiring is confirmed against.
"""

from __future__ import annotations

import pytest

from backend.models import CONTRACT_MODELS
from backend.models.examples import EXAMPLES_BY_CONTRACT


def test_contract_registry_is_importable_and_complete() -> None:
    assert CONTRACT_MODELS, "no contracts registered"
    assert set(EXAMPLES_BY_CONTRACT) == set(CONTRACT_MODELS)


@pytest.mark.parametrize(
    "model", list(CONTRACT_MODELS), ids=[m.__name__ for m in CONTRACT_MODELS]
)
def test_example_round_trips(model: type) -> None:
    example = EXAMPLES_BY_CONTRACT[model]
    assert isinstance(example, model)

    assert model.model_validate(example.model_dump()) == example
    assert model.model_validate_json(example.model_dump_json()) == example
