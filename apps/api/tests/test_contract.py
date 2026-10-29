"""Tests verifying that contract fixtures in contracts/ match backend Pydantic models."""

import json
from pathlib import Path

from research_desk.core.schemas import (
    AnalystOutput,
    ErrorEnvelope,
    HealthResponse,
    SourceDetailResponse,
)


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


def test_analyze_result_contract_fixture() -> None:
    contract_path = Path(__file__).parents[3] / "contracts" / "analyze_result.json"
    assert contract_path.exists(), f"Contract fixture missing: {contract_path}"

    with open(contract_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    validated = AnalystOutput.model_validate(data)
    assert validated.claim_count == 6
    assert len(validated.topics) == 2
    assert "AI Safety" in validated.topics


def test_source_detail_analyzed_contract_fixture() -> None:
    contract_path = Path(__file__).parents[3] / "contracts" / "source_detail_analyzed.json"
    assert contract_path.exists(), f"Contract fixture missing: {contract_path}"

    with open(contract_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    validated = SourceDetailResponse.model_validate(data)
    assert validated.source.id == "src_4f1b2c3d"
    assert validated.source.tag == "S1"
    assert validated.source.stages.analyzed is True
    assert len(validated.claims) == 2
    assert validated.claims[0].id == "clm_4f1b2c3d_00"
    assert validated.claims[0].importance == 5
    assert validated.claims[0].page_hint == 4
    assert validated.claims[1].page_hint == 7
    assert validated.summary is not None
    assert len(validated.topics) == 2
    assert "Multi-Agent Systems" in validated.topics
