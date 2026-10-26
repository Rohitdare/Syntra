"""Tests verifying that contract fixtures in contracts/ match backend Pydantic models."""

import json
from pathlib import Path

from research_desk.core.schemas import ErrorEnvelope, HealthResponse


def test_health_contract_fixture() -> None:
    contract_path = Path(__file__).parents[3] / "contracts" / "health.json"
    assert contract_path.exists(), f"Contract fixture missing: {contract_path}"

    with open(contract_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    validated = HealthResponse.model_validate(data)
    assert validated.ok is True
    assert validated.configured.gemini is True
    assert validated.configured.postgres is True
    assert validated.configured.qdrant is True


def test_error_contract_fixture() -> None:
    contract_path = Path(__file__).parents[3] / "contracts" / "error.json"
    assert contract_path.exists(), f"Contract fixture missing: {contract_path}"

    with open(contract_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    validated = ErrorEnvelope.model_validate(data)
    assert validated.error.code == "NO_TEXT"
    assert validated.error.request_id == "req_01j7x4z5k8m2n3p4q5r6s7t8u9"
    assert validated.error.retryable is False
    assert validated.error.retry_after_seconds is None
