"""OpenAPI-artifact tests — task P1-BE-16.

1. ``/openapi.json`` carries a schema for every top-level contract.
2. The committed ``openapi.json`` matches what the app emits now (fails if stale,
   so ``make openapi`` must be run and committed alongside any contract change).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.models import CONTRACT_MODELS
from scripts.export_openapi import OPENAPI_PATH, build_spec, render


def test_openapi_contains_every_contract_schema() -> None:
    spec = TestClient(create_app()).get("/openapi.json").json()
    schemas = spec["components"]["schemas"]

    missing = [m.__name__ for m in CONTRACT_MODELS if m.__name__ not in schemas]
    assert not missing, f"contracts absent from /openapi.json: {missing}"


def test_committed_openapi_artifact_is_current() -> None:
    assert OPENAPI_PATH.exists(), "openapi.json is missing — run `make openapi`"
    assert OPENAPI_PATH.read_text(encoding="utf-8") == render(build_spec()), (
        "openapi.json is out of date — run `make openapi` and commit the result"
    )
