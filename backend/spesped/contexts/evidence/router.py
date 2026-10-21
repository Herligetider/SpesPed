from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from spesped.audit import record_audit
from spesped.auth import Actor, get_actor, require_learner_access
from spesped.db import get_db
from spesped.errors import DomainError
from . import service
from .models import CorrectionImpact, Derivative, EvidenceRevision, ExtractionProposal, SourceItem
from .processing import MAX_BYTES
from .schemas import ConfirmEvidence, CorrectEvidence, Expected, IntakeMetadata, NoteIntake, ProposeField, RegisterDerivative, ReviewField, RecoverManualField

router = APIRouter(prefix="/api/v1/schools/{school_id}", tags=["evidence"])


def adapters(request):
    storage = getattr(request.app.state, "evidence_storage", None)
    if storage is None:
        raise DomainError("storage_unavailable", "Protected intake storage is not configured.", 503)
    scanner = getattr(request.app.state, "evidence_scanner", None)
    ocr = getattr(request.app.state, "evidence_ocr", None)
    if request.app.state.settings.environment != "test" and any(getattr(port, "synthetic", False) for port in (scanner, ocr)):
        raise DomainError("processing_configuration", "Synthetic processing is restricted to isolated tests.", 503)
    return storage, scanner, ocr


def commit(db):
    try:
        db.commit()
        db.info.pop("evidence_new_objects", None)
    except (IntegrityError, StaleDataError):
        cleanup(db)
        raise service.conflict("A concurrent command already changed this item. Refresh and retry.") from None
    except Exception:
        cleanup(db)
        raise


def cleanup(db):
    db.rollback()
    for storage, key in db.info.pop("evidence_new_objects", []):
        storage.delete(key)


def mutate(db, operation):
    try:
        value = operation()
        commit(db)
        return value
    except (IntegrityError, StaleDataError):
        cleanup(db)
        raise service.conflict("A concurrent command already changed this item. Refresh and retry.") from None
    except Exception:
        cleanup(db)
        raise


def source_view(db, row, revision=None):
    number = revision or row.current_revision
    rev = service.source_revision(db, row.school_id, row.id, number)
    inspected = service.inspection(db, row, number)
    return {"id": row.id, "version": row.version, "state": row.state, "current_revision": row.current_revision, "revision": number, "sender": rev.sender, "document_type": rev.document_type, "received_at": rev.received_at, "original_at": rev.original_at, "filename": rev.filename, "media_type": rev.media_type, "digest": rev.digest, "byte_size": rev.byte_size, "scan_state": inspected.scan_state, "extraction_state": inspected.extraction_state, "issue": inspected.issue, "page_count": len(inspected.pages), "review_progress": service.review_progress(db, row, number), "pagination": "logical_page_breaks" if rev.filename.endswith(".docx") else "source_pages"}


def proposal_view(row):
    return {key: getattr(row, key) for key in ("id", "version", "state", "source_id", "source_revision", "page", "span_start", "span_end", "field_name", "proposed_value", "reviewed_value", "outcome", "review_reason", "reviewer_id", "generation_job_id", "unit", "recovery_of_proposal_id")}


@router.post("/intake/notes", status_code=201)
def note(school_id: UUID, command: NoteIntake, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    storage, scanner, ocr = adapters(request)
    row, revision = mutate(db, lambda: service.submit(db, actor, str(school_id), command, command.text.encode(), "note.txt", storage, scanner, ocr, note=True))
    return source_view(db, row, revision)


async def upload_content(request):
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise DomainError("upload_size", "The upload exceeds 12582912 bytes.", 413)
        chunks.append(chunk)
    return b"".join(chunks)


def metadata_header(value):
    if len(value) > 4000:
        raise DomainError("intake_metadata", "Invalid intake metadata.", 422)
    try:
        return IntakeMetadata.model_validate_json(value)
    except ValidationError:
        raise DomainError("intake_metadata", "Supply valid typed intake metadata in X-Evidence-Metadata.", 422) from None


@router.post("/intake/files", status_code=201)
async def upload(school_id: UUID, request: Request, filename: str = Header(alias="X-Evidence-Filename"), metadata: str = Header(alias="X-Evidence-Metadata"), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    service.intake_access(db, actor, str(school_id))
    storage, scanner, ocr = adapters(request)
    command = metadata_header(metadata)
    content = await upload_content(request)
    row, revision = mutate(db, lambda: service.submit(db, actor, str(school_id), command, content, filename, storage, scanner, ocr))
    return source_view(db, row, revision)


@router.post("/intake/{source_id}/revisions", status_code=201)
async def revise(school_id: UUID, source_id: UUID, request: Request, expected_version: int = Header(alias="X-Expected-Version", ge=1), filename: str = Header(alias="X-Evidence-Filename"), metadata: str = Header(alias="X-Evidence-Metadata"), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    service.source(db, actor, str(school_id), str(source_id))
    storage, scanner, ocr = adapters(request)
    command = metadata_header(metadata)
    content = await upload_content(request)
    row, revision = mutate(db, lambda: service.submit(db, actor, str(school_id), command, content, filename, storage, scanner, ocr, replace_id=str(source_id), expected_version=expected_version))
    return source_view(db, row, revision)


@router.get("/intake")
def inbox(school_id: UUID, state: str | None = Query(None, max_length=30), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    service.intake_access(db, actor, str(school_id))
    query = select(SourceItem).where(SourceItem.school_id == str(school_id))
    if state:
        query = query.where(SourceItem.state == state)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(SourceItem.received_at.desc(), SourceItem.id).offset(offset).limit(limit)).all()
    record_audit(db, actor, str(school_id), "source.inbox_read", "school", str(school_id))
    commit(db)
    return {"items": [source_view(db, row) for row in rows], "total": total}


@router.get("/intake/{source_id}")
def get_source(school_id: UUID, source_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.source(db, actor, str(school_id), str(source_id))
    record_audit(db, actor, str(school_id), "source.read", "source", row.id)
    commit(db)
    return source_view(db, row)


@router.get("/intake/{source_id}/revisions/{revision}/original")
def original(school_id: UUID, source_id: UUID, revision: int, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.source(db, actor, str(school_id), str(source_id))
    rev = service.source_revision(db, row.school_id, row.id, revision)
    inspected = service.inspection(db, row, revision)
    if inspected.scan_state not in {"clean", "not_required_note"} or inspected.state == "quarantined":
        raise DomainError("source_quarantined", "The quarantined original cannot be previewed.", 409)
    storage, _, _ = adapters(request)
    content = service.read_original(storage, rev)
    record_audit(db, actor, str(school_id), "source.original_read", "source", row.id)
    commit(db)
    # Attachment forces downloading through the authorized route, never active inline HTML.
    return Response(content=content, media_type=rev.media_type, headers={"Content-Disposition": 'attachment; filename="source' + {"application/pdf": ".pdf", "text/plain": ".txt", "message/rfc822": ".eml"}.get(rev.media_type, ".bin") + '"', "Content-Security-Policy": "sandbox"})


@router.get("/intake/{source_id}/revisions/{revision}/pages/{page}")
def source_page(school_id: UUID, source_id: UUID, revision: int, page: int, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.source(db, actor, str(school_id), str(source_id))
    inspected = service.inspection(db, row, revision)
    if inspected is None or page < 1 or page > len(inspected.pages):
        raise DomainError("source_page", "This page is not available.", 404)
    text = inspected.pages[page - 1]
    record_audit(db, actor, str(school_id), "source.page_read", "source", row.id)
    commit(db)
    return {"page": page, "text": text, "source_revision": revision}


@router.post("/intake/{source_id}/inspect")
def inspect(school_id: UUID, source_id: UUID, command: Expected, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    storage, scanner, ocr = adapters(request)
    row = mutate(db, lambda: service.reprocess(db, actor, str(school_id), str(source_id), command.expected_version, storage, scanner, ocr))
    return source_view(db, row)


@router.get("/intake/{source_id}/proposals")
def proposals(school_id: UUID, source_id: UUID, request: Request, revision: int | None = Query(None, ge=1), origin: Literal['manual', 'model'] | None = None, outcome: Literal["pending", "accepted", "edited", "rejected"] | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.source(db, actor, str(school_id), str(source_id))
    query = select(ExtractionProposal).where(ExtractionProposal.school_id == str(school_id), ExtractionProposal.source_id == row.id, ExtractionProposal.source_revision == (revision or row.current_revision))
    if origin is not None:
        query = query.where(ExtractionProposal.generation_job_id.is_(None) if origin == 'manual' else ExtractionProposal.generation_job_id.is_not(None))
    if outcome:
        query = query.where(ExtractionProposal.outcome == outcome)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(ExtractionProposal.page, ExtractionProposal.span_start, ExtractionProposal.id).offset(offset).limit(limit)).all()
    for proposal in rows:
        service.require_proposal_model_access(db, actor, proposal, getattr(request.app.state, 'ai_gateway', None))
    record_audit(db, actor, str(school_id), "source.proposals_read", "source", row.id)
    commit(db)
    return {"items": [proposal_view(p) for p in rows], "total": total}


@router.get("/intake/{source_id}/proposals/recovery-candidates")
def recovery_candidates(school_id: UUID, source_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.source(db, actor, str(school_id), str(source_id))
    # Explicit metadata-only projection: never select generated/reviewed prose.
    query = select(ExtractionProposal.id, ExtractionProposal.source_id, ExtractionProposal.source_revision,
        ExtractionProposal.page, ExtractionProposal.span_start, ExtractionProposal.span_end, ExtractionProposal.field_name).where(
            ExtractionProposal.school_id == row.school_id, ExtractionProposal.source_id == row.id,
            ExtractionProposal.source_revision == row.current_revision, ExtractionProposal.generation_job_id.is_not(None))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(ExtractionProposal.page, ExtractionProposal.span_start, ExtractionProposal.id).offset(offset).limit(limit)).mappings().all()
    record_audit(db, actor, row.school_id, 'source.recovery_candidates_read', 'source', row.id)
    commit(db)
    return {'items': [dict(r) for r in rows], 'total': total}


@router.post("/intake/{source_id}/proposals", status_code=201)
def propose(school_id: UUID, source_id: UUID, command: ProposeField, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = mutate(db, lambda: service.propose(db, actor, str(school_id), str(source_id), command, getattr(request.app.state, 'ai_gateway', None)))
    return proposal_view(row)


@router.post("/intake/{source_id}/proposals/manual-recovery", status_code=201)
def recover_manual_field(school_id: UUID, source_id: UUID, command: RecoverManualField, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = mutate(db, lambda: service.recover_manual_field(db, actor, str(school_id), str(source_id), command, getattr(request.app.state, 'ai_gateway', None)))
    return proposal_view(row)


@router.post("/extraction-proposals/{proposal_id}/review")
def review(school_id: UUID, proposal_id: UUID, command: ReviewField, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = mutate(db, lambda: service.review(db, actor, str(school_id), str(proposal_id), command, getattr(request.app.state, 'ai_gateway', None)))
    return proposal_view(row)


@router.post("/extraction-proposals/{proposal_id}/confirm", status_code=201)
def confirm(school_id: UUID, proposal_id: UUID, command: ConfirmEvidence, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = mutate(db, lambda: service.confirm(db, actor, str(school_id), str(proposal_id), command, getattr(request.app.state, "evidence_goal_validator", None), runtime=getattr(request.app.state, "ai_gateway", None)))
    return service.evidence_view(db, row)


@router.get("/learners/{learner_id}/timeline")
def timeline(school_id: UUID, learner_id: UUID, date_basis: Literal["occurred", "recorded"] = "occurred", start: datetime | None = None, end: datetime | None = None, topic: str | None = Query(None, max_length=100), goal_revision_id: UUID | None = None, source_id: UUID | None = None, document_type: str | None = Query(None, max_length=80), query: str | None = Query(None, min_length=1, max_length=200), certainty: Literal["confirmed", "uncertain", "disputed"] | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    if any(t is not None and (t.tzinfo is None or t.utcoffset() is None) for t in (start, end)):
        raise DomainError("period", "Timeline bounds require timezone-aware instants.", 422)
    return service.timeline(db, actor, str(school_id), str(learner_id), date_basis=date_basis, start=start, end=end, topic=topic, goal_revision_id=goal_revision_id, source_id=source_id, document_type=document_type, query=query, certainty=certainty, offset=offset, limit=limit)


@router.get("/evidence/{evidence_id}")
def get_evidence(school_id: UUID, evidence_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.evidence(db, actor, str(school_id), str(evidence_id))
    record_audit(db, actor, str(school_id), "evidence.read", "evidence", row.id)
    commit(db)
    return service.evidence_view(db, row)


@router.get("/source-excerpts/{link_id}")
def excerpt(school_id: UUID, link_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    value = service.excerpt_view(db, actor, str(school_id), str(link_id))
    record_audit(db, actor, str(school_id), "evidence.excerpt_read", "source_excerpt", str(link_id))
    commit(db)
    return value


@router.post("/evidence/{evidence_id}/corrections")
def correct(school_id: UUID, evidence_id: UUID, command: CorrectEvidence, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = mutate(db, lambda: service.correct(db, actor, str(school_id), str(evidence_id), command, getattr(request.app.state, "evidence_goal_validator", None)))
    return service.evidence_view(db, row)


@router.get("/evidence/{evidence_id}/history")
def history(school_id: UUID, evidence_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.evidence(db, actor, str(school_id), str(evidence_id))
    statement = select(EvidenceRevision).where(EvidenceRevision.school_id == str(school_id), EvidenceRevision.evidence_id == row.id, EvidenceRevision.learner_id == row.learner_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    revisions = db.scalars(statement.order_by(EvidenceRevision.revision.desc()).offset(offset).limit(limit))
    return {"items": [{key: getattr(r, key) for key in ("revision", "content", "occurred_at", "recorded_at", "recorded_by", "certainty", "correction_reason")} for r in revisions], "total": total}


@router.post("/evidence/{evidence_id}/derivatives", status_code=201)
def derivative(school_id: UUID, evidence_id: UUID, command: RegisterDerivative, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = mutate(db, lambda: service.register_derivative(db, actor, str(school_id), str(evidence_id), command))
    return {"id": row.id, "version": row.version, "state": row.state}


@router.get("/learners/{learner_id}/evidence-derivatives")
def derivatives(school_id: UUID, learner_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_learner_access(db, actor, str(school_id), str(learner_id), "evidence.read")
    statement = select(Derivative).where(Derivative.school_id == str(school_id), Derivative.learner_id == str(learner_id))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(Derivative.id).offset(offset).limit(limit)).all()
    return {"items": [{key: getattr(row, key) for key in ("id", "version", "state", "target_type", "target_id", "target_revision", "evidence_id", "evidence_revision")} for row in rows], "total": total}


@router.get("/evidence/{evidence_id}/correction-impacts")
def impacts(school_id: UUID, evidence_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.evidence(db, actor, str(school_id), str(evidence_id))
    statement = select(CorrectionImpact).join(Derivative, Derivative.id == CorrectionImpact.derivative_id).where(CorrectionImpact.school_id == str(school_id), CorrectionImpact.evidence_id == row.id, Derivative.learner_id == row.learner_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(CorrectionImpact.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [{key: getattr(impact, key) for key in ("id", "old_revision", "new_revision", "derivative_id", "disposition", "created_at")} for impact in rows], "total": total}


from .schemas import ApplyStructuring, CreateClarification, ReassignClarification, ResolveClarification, ReopenClarification
from .models import ClarificationTask, ClarificationTransition


def clarification_view(task):
    return {key: getattr(task, key) for key in ('id', 'version', 'state', 'source_id', 'source_revision',
        'proposal_id', 'field_name', 'assignee_id', 'reason', 'detail', 'page', 'span_start', 'span_end', 'resolution', 'resolved_by', 'resolved_at')}


@router.post('/intake/{source_id}/structuring/apply', status_code=201)
def apply_structuring(school_id: UUID, source_id: UUID, command: ApplyStructuring, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    from spesped.contexts.platform.router import runtime
    result = mutate(db, lambda: service.apply_structuring(db, actor, str(school_id), str(source_id), command, runtime(request)))
    return {key: getattr(result, key) for key in ('id', 'version', 'state', 'source_id', 'source_revision', 'job_id', 'attempt_number')}


@router.post('/intake/{source_id}/clarifications', status_code=201)
def create_clarification(school_id: UUID, source_id: UUID, command: CreateClarification, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return clarification_view(mutate(db, lambda: service.create_clarification(db, actor, str(school_id), str(source_id), command, getattr(request.app.state, 'ai_gateway', None))))


@router.get('/intake/{source_id}/clarifications')
def list_clarifications(school_id: UUID, source_id: UUID, state: Literal['open', 'resolved'] | None = None, revision: int | None = Query(None, ge=1), assignee_id: UUID | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = service.source(db, actor, str(school_id), str(source_id))
    query = select(ClarificationTask).where(ClarificationTask.school_id == str(school_id), ClarificationTask.source_id == row.id)
    for column, value in ((ClarificationTask.state, state), (ClarificationTask.source_revision, revision), (ClarificationTask.assignee_id, str(assignee_id) if assignee_id else None)):
        if value is not None:
            query = query.where(column == value)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(ClarificationTask.created_at, ClarificationTask.id).offset(offset).limit(limit)).all()
    record_audit(db, actor, str(school_id), 'source.clarifications_read', 'source', row.id)
    commit(db)
    return {'items': [clarification_view(t) for t in rows], 'total': total}


@router.get('/intake/{source_id}/clarifications/{task_id}')
def get_clarification(school_id: UUID, source_id: UUID, task_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    _, task = service.get_clarification(db, actor, str(school_id), str(source_id), str(task_id))
    history = db.scalars(select(ClarificationTransition).where(ClarificationTransition.school_id == str(school_id), ClarificationTransition.task_id == task.id).order_by(ClarificationTransition.task_version)).all()
    result = clarification_view(task) | {'history': [{k: getattr(h, k) for k in ('task_version', 'actor_id', 'assignee_id', 'action', 'state', 'explanation', 'occurred_at')} for h in history]}
    record_audit(db, actor, str(school_id), 'source.clarification_read', 'clarification', task.id)
    commit(db)
    return result


@router.post('/intake/{source_id}/clarifications/{task_id}/reassign')
def reassign_clarification(school_id: UUID, source_id: UUID, task_id: UUID, command: ReassignClarification, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return clarification_view(mutate(db, lambda: service.change_clarification(db, actor, str(school_id), str(source_id), str(task_id), command, 'reassigned')))


@router.post('/intake/{source_id}/clarifications/{task_id}/resolve')
def resolve_clarification(school_id: UUID, source_id: UUID, task_id: UUID, command: ResolveClarification, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return clarification_view(mutate(db, lambda: service.change_clarification(db, actor, str(school_id), str(source_id), str(task_id), command, 'resolved')))


@router.post('/intake/{source_id}/clarifications/{task_id}/reopen')
def reopen_clarification(school_id: UUID, source_id: UUID, task_id: UUID, command: ReopenClarification, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return clarification_view(mutate(db, lambda: service.change_clarification(db, actor, str(school_id), str(source_id), str(task_id), command, 'reopened')))
