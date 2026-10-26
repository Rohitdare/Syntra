"""Unit tests for core/ids.py."""

import uuid

from research_desk.core.ids import (
    RESEARCH_DESK_NAMESPACE,
    brief_id,
    chunk_id,
    claim_id,
    key_to_point_id,
    normalize_question,
    pair_id,
    pair_key,
    project_id,
    short_hash,
    source_id,
)


def test_short_hash() -> None:
    h1 = short_hash("hello world")
    h2 = short_hash("hello world")
    assert h1 == h2
    assert len(h1) == 8
    assert int(h1, 16) >= 0


def test_normalize_question() -> None:
    raw = "   What   is   the   mechanism   of action?  \n\t "
    assert normalize_question(raw) == "What is the mechanism of action?"


def test_project_id_format() -> None:
    pid = project_id()
    assert pid.startswith("prj_")
    assert len(pid) == 12  # prj_ + 8 hex chars


def test_source_id_deterministic() -> None:
    s1 = source_id("prj_12345678", "sha256_abcdef")
    s2 = source_id("prj_12345678", "sha256_abcdef")
    s3 = source_id("prj_99999999", "sha256_abcdef")
    assert s1 == s2
    assert s1.startswith("src_")
    assert len(s1) == 12
    # Scoped per project
    assert s1 != s3


def test_chunk_and_claim_id_formatting() -> None:
    sid = "src_a1b2c3d4"
    cid = chunk_id(sid, 5)
    assert cid == "chk_a1b2c3d4_005"

    clid = claim_id(sid, 7)
    assert clid == "clm_a1b2c3d4_07"


def test_pair_key_and_verdict_id_order_independence() -> None:
    c1 = "clm_11111111_01"
    c2 = "clm_22222222_05"

    assert pair_key(c1, c2) == (c1, c2)
    assert pair_key(c2, c1) == (c1, c2)

    v1 = pair_id(c1, c2)
    v2 = pair_id(c2, c1)
    assert v1 == v2
    assert v1.startswith("vrd_")
    assert len(v1) == 12


def test_brief_id_normalization() -> None:
    pid = "prj_12345678"
    b1 = brief_id(pid, "What is climate change?")
    b2 = brief_id(pid, "  What   is   climate   change?  ")
    assert b1 == b2
    assert b1.startswith("brf_")
    assert len(b1) == 12


def test_key_to_point_id() -> None:
    pid = "prj_12345678"
    k1 = "chk_a1b2c3d4_001"
    pt1 = key_to_point_id(pid, k1)
    pt2 = key_to_point_id(pid, k1)
    pt3 = key_to_point_id("prj_87654321", k1)

    assert isinstance(pt1, uuid.UUID)
    assert pt1 == pt2
    # Project-scoped: different project yields different point ID
    assert pt1 != pt3
    expected = uuid.uuid5(RESEARCH_DESK_NAMESPACE, f"{pid}:{k1}")
    assert pt1 == expected
