"""Deterministic and project-scoped ID generation.

Follows docs/03-DATABASE-SCHEMA.md Section 4:
- Readable keys:
    prj_<8hex>
    src_<8hex>
    chk_<src8>_<nnn>
    clm_<src8>_<nn>
    vrd_<8hex>
    brf_<8hex>
- Qdrant point ID = UUIDv5(namespace, f"{project_id}:{key}")
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

# Fixed namespace UUID for Research Desk Qdrant points
RESEARCH_DESK_NAMESPACE = uuid.UUID("a74f469a-6531-4ce8-8f56-074900a89d41")


def short_hash(value: str) -> str:
    """Return the first 8 hex characters of the SHA-1 digest of value."""
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def normalize_question(question: str) -> str:
    """Normalize a research question by trimming and collapsing internal whitespace."""
    return " ".join(question.strip().split())


def project_id() -> str:
    """Generate a random 8-hex project ID key (prj_<8hex>)."""
    return f"prj_{secrets.token_hex(4)}"


def make_project_id() -> str:
    """Alias for project_id()."""
    return project_id()


def source_id(project_id: str, content_hash: str) -> str:
    """Build a deterministic source ID key from project_id and content_hash."""
    h = short_hash(f"{project_id}:{content_hash}")
    return f"src_{h}"


def make_source_id(project_id: str | None = None, content_hash: str | None = None) -> str:
    """Generate a source ID key.
    Deterministic if project_id and content_hash provided, otherwise random.
    """
    if project_id is not None and content_hash is not None:
        return source_id(project_id, content_hash)
    return f"src_{secrets.token_hex(4)}"


def chunk_id(src_id: str, chunk_index: int) -> str:
    """Build a deterministic chunk ID key (chk_<src8>_<nnn>)."""
    src8 = src_id.removeprefix("src_")
    return f"chk_{src8}_{chunk_index:03d}"


def make_chunk_id(src_id: str, chunk_index: int) -> str:
    """Alias for chunk_id()."""
    return chunk_id(src_id, chunk_index)


def claim_id(src_id: str, claim_index: int) -> str:
    """Build a deterministic claim ID key (clm_<src8>_<nn>)."""
    src8 = src_id.removeprefix("src_")
    return f"clm_{src8}_{claim_index:02d}"


def make_claim_id(src_id: str, claim_index: int) -> str:
    """Alias for claim_id()."""
    return claim_id(src_id, claim_index)


def pair_key(claim_id_a: str, claim_id_b: str) -> tuple[str, str]:
    """Return the sorted pair of claim keys (order-independent)."""
    if claim_id_a <= claim_id_b:
        return claim_id_a, claim_id_b
    return claim_id_b, claim_id_a


def pair_id(claim_id_a: str, claim_id_b: str) -> str:
    """Build a deterministic verdict key from two claim keys (vrd_<8hex of sorted pair>)."""
    first, second = pair_key(claim_id_a, claim_id_b)
    h = short_hash(f"{first}:{second}")
    return f"vrd_{h}"


def make_verdict_id(claim_id_a: str, claim_id_b: str) -> str:
    """Alias for pair_id()."""
    return pair_id(claim_id_a, claim_id_b)


def brief_id(project_id: str, question: str) -> str:
    """Build a deterministic brief ID key (brf_<8hex of project_id + normalized question>)."""
    norm = normalize_question(question)
    h = short_hash(f"{project_id}:{norm}")
    return f"brf_{h}"


def make_brief_id(project_id: str, question: str) -> str:
    """Alias for brief_id()."""
    return brief_id(project_id, question)


def key_to_point_id(project_id: str, key: str) -> uuid.UUID:
    """Generate a deterministic UUIDv5 for a Qdrant point from project_id and key."""
    name = f"{project_id}:{key}"
    return uuid.uuid5(RESEARCH_DESK_NAMESPACE, name)


# Aliases for convenience across tests and spikes
make_chunk_key = make_chunk_id
make_claim_key = make_claim_id
qdrant_point_id = key_to_point_id
