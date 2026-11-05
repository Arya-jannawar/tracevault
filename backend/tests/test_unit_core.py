"""Unit tests: chunking, provenance graph, fence/idempotency, auth."""
from __future__ import annotations

import uuid

import pytest

from app.chunking import chunk_text, split_sentences, token_overlap
from app.errors import IdempotencyConflict, PublicationBlocked


# ---------------------------------------------------------------- chunking
def test_chunk_offsets_roundtrip():
    content = ("Alpha paragraph with some text about storage systems.\n\n"
               "Beta paragraph discusses the Nightingale rollout on 14 March "
               "2026 with a budget of 4.2 crore rupees for the campuses.\n\n"
               "Gamma paragraph is here.\n\n"
               "Delta paragraph continues with retention rules and schedules "
               "for seven year archival of financial records.\n\n"
               "Final paragraph closes the document with a brief remark.")
    chunks = chunk_text(content)
    assert len(chunks) >= 2
    for c in chunks:
        assert content[c["start"]:c["end"]] == c["text"]
    # chunks cover the text without overlapping ranges
    ordered = sorted(chunks, key=lambda c: c["start"])
    for a, b in zip(ordered, ordered[1:]):
        assert a["end"] <= b["start"]


def test_long_paragraph_split_by_sentences():
    content = ("Sentence one is here. " * 40).strip()
    chunks = chunk_text(content)
    assert len(chunks) > 1
    assert all(len(c["text"]) < 1200 for c in chunks)


def test_sentence_split_offsets():
    text = "First sentence. Second one! Third?"
    sentences = split_sentences(text)
    assert [s["text"] for s in sentences] == ["First sentence.", "Second one!", "Third?"]
    for s in sentences:
        assert text[s["start"]:s["end"]] == s["text"]


def test_token_overlap():
    assert token_overlap("Aurora LMS training", "training on the Aurora LMS") > 0.5
    assert token_overlap("alpha beta", "gamma delta") == 0.0


# ---------------------------------------------------------------- provenance
def test_transitive_closure_multihop(db, workspace):
    from app.models import Artifact, ArtifactType, Relationship
    from app.provenance import register_artifact, register_edge, transitive_dependants

    a = register_artifact(db, workspace_id=workspace.id, type=ArtifactType.chunk)
    b = register_artifact(db, workspace_id=workspace.id, type=ArtifactType.summary)
    c = register_artifact(db, workspace_id=workspace.id, type=ArtifactType.answer)
    d = register_artifact(db, workspace_id=workspace.id, type=ArtifactType.cache_entry)
    register_edge(db, parent=a, child=b, relationship=Relationship.supports)
    register_edge(db, parent=b, child=c, relationship=Relationship.answers)
    register_edge(db, parent=c, child=d, relationship=Relationship.cached_as)

    deps = transitive_dependants(db, [a.id])
    assert set(deps) == {b.id, c.id, d.id}
    direct = __import__("app.provenance", fromlist=["direct_dependants"]).direct_dependants(db, [a.id])
    assert direct == [b.id]


def test_cycle_protection(db, workspace):
    from app.models import Artifact, ArtifactType, Relationship
    from app.provenance import register_artifact, register_edge, transitive_dependants

    a = register_artifact(db, workspace_id=workspace.id, type=ArtifactType.chunk)
    b = register_artifact(db, workspace_id=workspace.id, type=ArtifactType.summary)
    register_edge(db, parent=a, child=b, relationship=Relationship.supports)
    register_edge(db, parent=b, child=a, relationship=Relationship.supports)
    # terminates via visited set; both reachable
    deps = transitive_dependants(db, [a.id])
    assert set(deps) == {b.id}


def test_self_edge_rejected(db, workspace):
    from app.models import Artifact, ArtifactType, Relationship
    from app.provenance import register_artifact, register_edge

    a = register_artifact(db, workspace_id=workspace.id, type=ArtifactType.chunk)
    with pytest.raises(ValueError):
        register_edge(db, parent=a, child=a, relationship=Relationship.supports)


def test_cross_workspace_edge_rejected(db, workspace):
    from app.models import Artifact, ArtifactType, Relationship
    from app.provenance import register_artifact, register_edge

    a = register_artifact(db, workspace_id=workspace.id, type=ArtifactType.chunk)
    b = register_artifact(db, workspace_id=workspace.id + 1, type=ArtifactType.chunk)
    with pytest.raises(ValueError):
        register_edge(db, parent=a, child=b, relationship=Relationship.supports)


# ---------------------------------------------------------------- fence
def test_gate_publish_blocks_after_tombstone(db, workspace):
    from app.fence import gate_publish
    from app.models import Tombstone

    doc_id = uuid.uuid4()
    db.add(Tombstone(workspace_id=workspace.id, document_id=doc_id, fence_epoch=9))
    db.commit()
    with pytest.raises(PublicationBlocked):
        gate_publish(db, workspace.id, [doc_id])


def test_deletion_acceptance_idempotency(db, workspace):
    from app.ingestion import create_document
    from app.deletion import accept_deletion

    doc = create_document(db, workspace_id=workspace.id, title="T", content="hello " * 50)
    r1, created1 = accept_deletion(db, workspace_id=workspace.id, document_id=doc.id,
                                   idempotency_key="idem-key-001")
    r2, created2 = accept_deletion(db, workspace_id=workspace.id, document_id=doc.id,
                                   idempotency_key="idem-key-001")
    assert created1 is True and created2 is False
    assert r1.id == r2.id
    with pytest.raises(IdempotencyConflict):
        other = create_document(db, workspace_id=workspace.id, title="U",
                                content="world " * 50)
        accept_deletion(db, workspace_id=workspace.id, document_id=other.id,
                        idempotency_key="idem-key-001")


def test_fence_generation_bumps_on_acceptance(db, workspace):
    from app.deletion import accept_deletion
    from app.ingestion import create_document

    doc = create_document(db, workspace_id=workspace.id, title="F", content="x " * 60)
    before = workspace.fence_generation
    request, _ = accept_deletion(db, workspace_id=workspace.id, document_id=doc.id,
                                 idempotency_key="fence-key-001")
    db.refresh(workspace)
    assert workspace.fence_generation == before + 1
    assert request.fence_epoch == workspace.fence_generation


# ---------------------------------------------------------------- auth
def test_password_hash_roundtrip():
    from app.auth import hash_password, verify_password

    stored = hash_password("s3cret-password")
    assert verify_password("s3cret-password", stored)
    assert not verify_password("wrong", stored)


def test_session_token_tamper_rejection(settings):
    from app.auth import make_session_token, read_session_token
    from app.errors import AuthFailed

    token = make_session_token("admin", "operator")
    payload = read_session_token(token)
    assert payload["u"] == "admin"
    with pytest.raises(AuthFailed):
        read_session_token(token[:-2] + "xx")


# ---------------------------------------------------------------- metrics
def test_na_on_zero_denominator():
    from app.evaluation import _na

    assert _na(0, 0) == "N/A"
    assert _na(1, 0) == "N/A"
    assert _na(3, 4) == 0.75
