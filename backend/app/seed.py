"""Original deterministic synthetic corpus (no real personal data) + demo/eval
seeding. The corpus encodes the required scenario patterns:

* docA: unique fact (Nightingale rollout) + shared fact (Aurora LMS training)
* docB: the same shared fact (independent support) + its own unique fact
* docC/docH: unrelated content that must survive deletion of docA
* docD: contradictory number vs docA; docE/docK: negated statements
* docF: superseded version (v1 -> v2)
* docG: transitive summary-of-summary chain (summaryG -> answerSoS)
* docI/docJ/docL: identifier/numerical probe targets
* summaryAB: multi-source summary (docA unique + docB shared) — the repair case
* unknown-provenance artifact: seeded only in isolated evaluation workspaces

Seeding is idempotent (skips if the workspace already has documents).
"""
from __future__ import annotations

import uuid as uuidlib

from sqlalchemy.orm import Session

from .ingestion import create_document
from .models import (
    Artifact,
    ArtifactType,
    Claim,
    ClaimStatus,
    ClaimSupport,
    Document,
    Relationship,
    Summary,
)
from .provenance import register_artifact, register_edge

CORPUS: dict[str, dict] = {
    "docA": {
        "title": "Project Nightingale Phase 2 Brief",
        "content": (
            "Project Nightingale Phase 2 Brief\n\n"
            "The Nightingale phase 2 rollout is scheduled for 14 March 2026 with a "
            "budget of 4.2 crore rupees. The rollout covers the Pune and Nagpur "
            "campuses in the first wave.\n\n"
            "All engineering staff must complete the quarterly security compliance "
            "training on the Aurora LMS before 30 June. Completion is tracked "
            "automatically by the learning platform."
        ),
    },
    "docB": {
        "title": "Aurora LMS Training Calendar",
        "content": (
            "Aurora LMS Training Calendar\n\n"
            "All engineering staff must complete the quarterly security compliance "
            "training on the Aurora LMS before 30 June. The compliance module is "
            "updated every quarter by the security office.\n\n"
            "The Aurora LMS maintenance window is the first Sunday of each month "
            "from 02:00 to 05:00 IST. Courses are unavailable during maintenance."
        ),
    },
    "docC": {
        "title": "Cafeteria Menu Rotation",
        "content": (
            "Cafeteria Menu Rotation\n\n"
            "The cafeteria rotates its menu weekly. Italian cuisine is served on "
            "Wednesdays. The juice bar opens at 08:30 on weekdays.\n\n"
            "Friday specials are announced on the intranet notice board every "
            "Monday morning."
        ),
    },
    "docD": {
        "title": "Nightingale Budget Addendum",
        "content": (
            "Nightingale Budget Addendum\n\n"
            "Internal estimates place the Nightingale phase 2 budget at 6.8 crore "
            "rupees, pending finance review. The addendum does not change the "
            "published rollout schedule.\n\n"
            "A revised estimate will be circulated after the finance committee "
            "meeting next quarter."
        ),
    },
    "docE": {
        "title": "Remote Work Policy",
        "content": (
            "Remote Work Policy\n\n"
            "The company does not permit full-time remote employment. Hybrid "
            "attendance of three days per week is required for all campus roles.\n\n"
            "Exceptions require written approval from the department head and HR."
        ),
    },
    "docF": {
        "title": "Vendor Onboarding Checklist",
        "content": (
            "Vendor Onboarding Checklist\n\n"
            "Vendor onboarding requires three references and a signed NDA before "
            "procurement approval. The checklist is maintained by the purchasing "
            "office.\n\n"
            "Vendors must renew their registration every fiscal year."
        ),
    },
    "docG": {
        "title": "Quarterly Business Review Summary",
        "content": (
            "Quarterly Business Review Summary\n\n"
            "The quarterly business review reported steady growth in campus "
            "services and a 12 percent rise in training completion rates. "
            "Facilities upgrades remain on schedule.\n\n"
            "The next review is planned for the first week of July."
        ),
    },
    "docH": {
        "title": "Library Renovation Notice",
        "content": (
            "Library Renovation Notice\n\n"
            "The central library will renovate its second floor reading room from "
            "May to August. Temporary seating is available on the ground floor.\n\n"
            "Book returns are unaffected by the renovation work."
        ),
    },
    "docI": {
        "title": "Data Retention Schedule",
        "content": (
            "Data Retention Schedule\n\n"
            "Financial records are retained for seven years. Meeting recordings "
            "are deleted after 90 days.\n\n"
            "Departments must review their stored data twice a year against this "
            "schedule."
        ),
    },
    "docJ": {
        "title": "Fitness Center Hours",
        "content": (
            "Fitness Center Hours\n\n"
            "The fitness center is open from 06:00 to 22:00 on weekdays and from "
            "07:00 to 20:00 on weekends. The pool closes 30 minutes earlier.\n\n"
            "Members must carry their campus ID at all times."
        ),
    },
    "docK": {
        "title": "Product Launch FAQ",
        "content": (
            "Product Launch FAQ\n\n"
            "The Helio keyboard ships with a USB-C cable. It does not include a "
            "wrist rest; the accessory is sold separately.\n\n"
            "Pre-orders open on 1 April with a two-week delivery window."
        ),
    },
    "docL": {
        "title": "Transit Subsidy Program",
        "content": (
            "Transit Subsidy Program\n\n"
            "Employees with a monthly transit pass can claim a 40 percent subsidy "
            "through the payroll portal. Claims must be filed within 30 days of "
            "purchase.\n\n"
            "The program budget is reviewed annually."
        ),
    },
}

SUMMARY_AB_CONTENT = (
    "The Nightingale phase 2 rollout is scheduled for 14 March 2026 with a budget "
    "of 4.2 crore rupees. All engineering staff must complete the quarterly "
    "security compliance training on the Aurora LMS before 30 June."
)


def seed_demo_workspace(db: Session, workspace_id: int) -> dict:
    """Seed the demo corpus + the multi-source summary + transitive answer.
    Idempotent: skips when documents already exist. Ingestion runs through the
    durable job queue."""
    existing = db.query(Document).filter_by(workspace_id=workspace_id).count()
    if existing >= len(CORPUS):
        return {"status": "already_seeded", "documents": existing}

    created = []
    for key, spec in CORPUS.items():
        doc = create_document(
            db, workspace_id=workspace_id, title=spec["title"],
            content=spec["content"], source_type="txt",
        )
        va = (
            db.query(Artifact)
            .filter_by(document_id=doc.id, type=ArtifactType.document_version)
            .one()
        )
        va.meta = {**(va.meta or {}), "gold_key": key}
        created.append(str(doc.id))
    db.commit()
    _seed_summary_ab(db, workspace_id)
    db.commit()
    return {"status": "seeded", "documents": len(created)}


def _seed_summary_ab(db: Session, workspace_id: int) -> None:
    """Multi-source summary: claim 1 supported ONLY by docA (deleted with it),
    claim 2 independently supported by docB (must survive repair)."""
    doc_a = db.query(Document).filter(
        Document.title == CORPUS["docA"]["title"]).first()
    doc_b = db.query(Document).filter(
        Document.title == CORPUS["docB"]["title"]).first()
    if doc_a is None or doc_b is None:
        return
    existing_summaries = (
        db.query(Artifact)
        .filter_by(workspace_id=workspace_id, type=ArtifactType.summary)
        .all()
    )
    if any((a.meta or {}).get("gold_key") == "summaryAB" for a in existing_summaries):
        return
    va_a = (
        db.query(Artifact)
        .filter_by(document_id=doc_a.id, type=ArtifactType.document_version).one()
    )
    chunk_a = (
        db.query(Artifact)
        .filter_by(document_id=doc_a.id, type=ArtifactType.chunk)
        .order_by(Artifact.id)
        .first()
    )
    chunk_b = (
        db.query(Artifact)
        .filter_by(document_id=doc_b.id, type=ArtifactType.chunk)
        .order_by(Artifact.id)
        .first()
    )
    if chunk_a is None or chunk_b is None:
        return  # ingestion not finished yet; re-run seeds after worker completes

    summary_art = register_artifact(
        db, workspace_id=workspace_id, type=ArtifactType.summary,
        document_id=doc_a.id, document_version_id=va_a.document_version_id,
        meta={"summary_version": 1, "mode": "seed_multisource",
              "gold_key": "summaryAB"},
    )
    db.add(Summary(artifact_id=summary_art.id, content=SUMMARY_AB_CONTENT,
                   summary_version=1))
    register_edge(db, parent=va_a, child=summary_art,
                  relationship=Relationship.summarizes)
    claims = [
        ("The Nightingale phase 2 rollout is scheduled for 14 March 2026 with a "
         "budget of 4.2 crore rupees.", chunk_a, doc_a.id),
        ("All engineering staff must complete the quarterly security compliance "
         "training on the Aurora LMS before 30 June.", chunk_b, doc_b.id),
    ]
    for i, (text, src_chunk, doc_id) in enumerate(claims):
        claim = Claim(summary_artifact_id=summary_art.id, idx=i, text=text,
                      status=ClaimStatus.supported.value)
        db.add(claim)
        db.flush()
        db.add(ClaimSupport(claim_id=claim.id, source_artifact_id=src_chunk.id,
                            document_id=doc_id, source_version=1,
                            offsets={"start": (src_chunk.meta or {}).get("start"),
                                     "end": (src_chunk.meta or {}).get("end")}))
        register_edge(db, parent=src_chunk, child=summary_art,
                      relationship=Relationship.supports)
    db.flush()


def tag_pipeline_artifacts(db: Session, workspace_id: int) -> None:
    """Give pipeline-generated artifacts gold_keys (idempotent); used by eval."""
    summaries = (
        db.query(Artifact)
        .filter_by(workspace_id=workspace_id, type=ArtifactType.summary)
        .all()
    )
    for s in summaries:
        if (s.meta or {}).get("gold_key"):
            continue
        doc = db.get(Document, s.document_id) if s.document_id else None
        va = (
            db.query(Artifact)
            .filter_by(document_id=s.document_id,
                       type=ArtifactType.document_version)
            .first()
            if s.document_id else None
        )
        key = (va.meta or {}).get("gold_key") if va else None
        if key and doc is not None:
            s.meta = {**(s.meta or {}), "gold_key": f"summary_auto_{key}"}
    db.commit()
