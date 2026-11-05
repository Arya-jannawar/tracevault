"""Document routes: upload, search/list, detail, chunks, versions,
deletion impact preview, deletion (acceptance), content access."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from ..chunking import chunk_text
from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user, get_workspace, require_operator
from ..errors import ContentBlocked, NotFound, UnsupportedContent, ValidationFailed
from ..fence import assert_document_not_fenced
from ..ingestion import create_document
from ..models import (
    Artifact,
    ArtifactType,
    DeletionRequest,
    DeletionState,
    Document,
    DocumentState,
    DocumentVersion,
    LifecycleState,
    Tombstone,
)
from ..provenance import affected_set_for_document
from ..schemas import (
    ChunkOut,
    DeletionImpact,
    DeletionRequestOut,
    DocumentDetail,
    DocumentOut,
    DocumentVersionOut,
)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_TYPES = {"txt": ".txt", "md": ".md", "pdf": ".pdf"}


def _extract_pdf(data: bytes) -> str:
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedContent(
            "PDF extraction is unavailable in this environment (PyMuPDF not "
            "installed). Upload TXT or Markdown, or install backend "
            "requirements. OCR for scanned PDFs is not implemented."
        ) from exc
    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            pages = [page.get_text() for page in pdf]
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedContent(
            "This PDF could not be parsed (encrypted or malformed)."
        ) from exc
    text = "\n\n".join(pages).strip()
    if not text:
        raise UnsupportedContent(
            "No extractable text found in this PDF. Scanned/image-only PDFs are "
            "not supported because OCR is not implemented."
        )
    return text


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    request: Request,
    file: UploadFile | None = File(default=None),
    title: str | None = Form(default=None),
    content: str | None = Form(default=None),
    source_type: str = Form(default="txt"),
    db: Session = Depends(get_db),
    ws=Depends(get_workspace),
    user=Depends(require_operator),
):
    settings = get_settings()
    if file is not None:
        data = file.file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise ValidationFailed(
                f"Upload exceeds the {settings.max_upload_mb} MB limit."
            )
        name = (file.filename or "upload.txt").split("/")[-1].split("\\")[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "txt"
        if ext == "pdf":
            text = _extract_pdf(data)
            stype = "pdf"
        elif ext in ("txt", "md"):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise UnsupportedContent(
                    "Only UTF-8 text files are supported."
                ) from exc
            stype = ext
        else:
            raise UnsupportedContent(
                f"Unsupported file type '{ext}'. Allowed: txt, md, pdf "
                "(text-based PDFs only; scanned PDFs are not supported)."
            )
        doc_title = (title or name).strip() or name
    else:
        if not content or not content.strip():
            raise ValidationFailed("Provide a file upload or non-empty content.")
        text = content
        stype = source_type if source_type in ("txt", "md") else "txt"
        doc_title = (title or "Untitled document").strip()

    if len(chunk_text(text)) > settings.max_chunks_per_doc:
        raise ValidationFailed(
            f"Document would exceed {settings.max_chunks_per_doc} chunks."
        )
    doc = create_document(db, workspace_id=ws.id, title=doc_title,
                          content=text, source_type=stype)
    return _document_out(db, doc)


def _counts(db: Session, document_id: uuid.UUID) -> dict:
    rows = (
        db.query(Artifact.type, Artifact.id)
        .filter(
            Artifact.document_id == document_id,
            Artifact.lifecycle_state != LifecycleState.removed.value,
        )
        .all()
    )
    out = {"chunk": 0, "summary": 0, "answer": 0, "cache_entry": 0}
    for atype, _ in rows:
        if atype.value in out:
            out[atype.value] += 1
    return out


def _document_out(db: Session, doc: Document) -> DocumentOut:
    counts = _counts(db, doc.id)
    return DocumentOut(
        id=str(doc.id), title=doc.title, state=doc.state,
        created_at=doc.created_at, updated_at=doc.updated_at,
        version_count=db.query(DocumentVersion).filter_by(document_id=doc.id).count(),
        chunk_count=counts["chunk"], summary_count=counts["summary"],
        answer_count=counts["answer"], cache_count=counts["cache_entry"],
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(
    q: str | None = Query(default=None),
    state: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    ws=Depends(get_workspace),
    user=Depends(get_current_user),
):
    query = db.query(Document).filter_by(workspace_id=ws.id)
    if state:
        query = query.filter(Document.state == state)
    if q:
        query = query.filter(Document.title.ilike(f"%{q}%"))
    docs = (
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_document_out(db, d) for d in docs]


def _get_doc(db: Session, ws, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.workspace_id != ws.id:
        raise NotFound("Document not found.")
    return doc


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db),
                 ws=Depends(get_workspace), user=Depends(get_current_user)):
    doc = _get_doc(db, ws, document_id)
    base = _document_out(db, doc)
    versions = db.query(DocumentVersion).filter_by(document_id=doc.id).all()
    return DocumentDetail(
        **base.model_dump(),
        versions=[
            DocumentVersionOut(
                id=str(v.id), version=v.version, source_type=v.source_type,
                filename=v.filename if v.content_state == "active" else "[removed]",
                checksum=v.checksum, content_state=v.content_state,
                created_at=v.created_at,
            )
            for v in versions
        ],
        coverage_notes=[] if doc.state == DocumentState.active.value
        else ["This document is tombstoned/deleted; content is redacted."],
    )


@router.get("/{document_id}/content")
def get_document_content(document_id: uuid.UUID, db: Session = Depends(get_db),
                         ws=Depends(get_workspace),
                         user=Depends(get_current_user)):
    doc = _get_doc(db, ws, document_id)
    assert_document_not_fenced(db, ws.id, doc.id)
    version = db.get(DocumentVersion, doc.current_version_id)
    if version is None or version.content_state != "active":
        raise ContentBlocked("Document content has been removed by a deletion request.")
    return {"document_id": str(doc.id), "title": doc.title, "content": version.content}


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
def get_document_chunks(document_id: uuid.UUID, db: Session = Depends(get_db),
                        ws=Depends(get_workspace), user=Depends(get_current_user)):
    doc = _get_doc(db, ws, document_id)
    assert_document_not_fenced(db, ws.id, doc.id)
    arts = (
        db.query(Artifact)
        .filter_by(document_id=doc.id, type=ArtifactType.chunk)
        .order_by(Artifact.id)
        .all()
    )
    return [
        ChunkOut(
            artifact_id=str(a.id), index=(a.meta or {}).get("index", 0),
            start=(a.meta or {}).get("start", 0), end=(a.meta or {}).get("end", 0),
            text=(a.meta or {}).get("text")
            if a.lifecycle_state == LifecycleState.active.value else None,
            lifecycle_state=a.lifecycle_state,
        )
        for a in arts
    ]


@router.get("/{document_id}/versions", response_model=list[DocumentVersionOut])
def get_document_versions(document_id: uuid.UUID, db: Session = Depends(get_db),
                          ws=Depends(get_workspace), user=Depends(get_current_user)):
    doc = _get_doc(db, ws, document_id)
    versions = db.query(DocumentVersion).filter_by(document_id=doc.id).all()
    return [
        DocumentVersionOut(
            id=str(v.id), version=v.version, source_type=v.source_type,
            filename=v.filename if v.content_state == "active" else "[removed]",
            checksum=v.checksum, content_state=v.content_state,
            created_at=v.created_at,
        )
        for v in versions
    ]


@router.get("/{document_id}/deletion-impact", response_model=DeletionImpact)
def deletion_impact(document_id: uuid.UUID, db: Session = Depends(get_db),
                    ws=Depends(get_workspace), user=Depends(get_current_user)):
    doc = _get_doc(db, ws, document_id)
    affected, warnings = affected_set_for_document(db, doc.id, ws.id)
    by_type: dict[str, int] = {}
    for a in affected:
        by_type[a.type.value] = by_type.get(a.type.value, 0) + 1
    return DeletionImpact(
        document_id=str(doc.id),
        affected_count=len(affected),
        affected_by_type=by_type,
        coverage_warnings=warnings,
        scope_exclusions=[
            "Unmanaged backups, snapshots, WAL archives",
            "External provider telemetry and logs",
            "Previously disclosed answers and unmanaged client copies",
            "Replicas or stores without an integrated connector",
        ],
    )


@router.delete("/{document_id}", response_model=DeletionRequestOut, status_code=202)
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db),
                    ws=Depends(get_workspace), user=Depends(require_operator)):
    from ..deletion import accept_deletion

    doc = _get_doc(db, ws, document_id)
    request, _created = accept_deletion(
        db, workspace_id=ws.id, document_id=doc.id,
        idempotency_key=f"ui-{uuid.uuid4().hex}",
        requested_by=user.username,
    )
    return _deletion_out(request)


def _deletion_out(r: DeletionRequest) -> DeletionRequestOut:
    return DeletionRequestOut(
        id=str(r.id), document_id=str(r.document_id), state=r.state,
        fence_epoch=r.fence_epoch, repair_enabled=r.repair_enabled,
        accepted_at=r.accepted_at, started_at=r.started_at,
        finished_at=r.finished_at, failure_reason=r.failure_reason,
        report=r.report,
    )
