"""Transaction-participating evidence commands; callers commit or roll back."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from spesped.audit import record_audit
from spesped.auth import require_authority, require_learner_access
from spesped.db import utcnow
from spesped.errors import DomainError, access_denied
from .models import CorrectionImpact, Derivative, EvidenceEvent, EvidenceItem, EvidenceRevision, ExtractionProposal, Inspection, IntakeCommand, SourceItem, SourceRevision, SourceSubjectLink
from .processing import ProcessingUnavailable, UnsafeFile, bounded_extract, inspect_type
from .schemas import validate_field


def conflict(message="The item changed. Refresh before retrying."):
    return DomainError("revision_conflict", message, 409)


def intake_access(db, actor, school_id):
    return require_authority(db, actor, school_id, "evidence.intake")


def event(db, actor, school_id, action, row, **payload):
    db.flush()
    record_audit(db, actor, school_id, action, "evidence", row.id)
    db.add(EvidenceEvent(school_id=school_id, aggregate_id=row.id, aggregate_version=row.version, event_type=action, payload=payload))


def source(db, actor, school_id, source_id, *, lock=False):
    intake_access(db, actor, school_id)
    statement = select(SourceItem).where(SourceItem.id == source_id, SourceItem.school_id == school_id)
    if lock:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise access_denied()
    return row


def source_revision(db, school_id, source_id, revision):
    row = db.scalar(select(SourceRevision).where(SourceRevision.school_id == school_id, SourceRevision.source_id == source_id, SourceRevision.revision == revision))
    if row is None:
        raise access_denied()
    return row


def inspection(db, row, revision=None):
    return db.scalar(select(Inspection).where(Inspection.school_id == row.school_id, Inspection.source_id == row.id, Inspection.source_revision == (revision or row.current_revision)))


def check_version(row, expected):
    if row.version != expected:
        raise conflict()


def fingerprint(metadata, content, filename, replace_id=None, expected_version=None):
    return hashlib.sha256(json.dumps({"metadata": metadata.model_dump(mode="json"), "content_digest": hashlib.sha256(content).hexdigest(), "filename": filename, "replace_id": replace_id, "expected_version": expected_version}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def submit(db, actor, school_id, metadata, content, filename, storage, scanner=None, ocr=None, *, note=False, replace_id=None, expected_version=None):
    intake_access(db, actor, school_id)
    extension, media_type = inspect_type(filename, content)
    if len(filename) > 200 or Path(filename).name != filename:
        raise DomainError("filename", "Supply a plain filename of at most 200 characters.", 422)
    digest = hashlib.sha256(content).hexdigest()
    command_digest = fingerprint(metadata, content, filename, replace_id, expected_version)
    prior = db.scalar(select(IntakeCommand).where(IntakeCommand.school_id == school_id, IntakeCommand.request_key == metadata.request_key))
    if prior:
        if prior.request_digest != command_digest or (replace_id and prior.source_id != replace_id):
            raise DomainError("idempotency_conflict", "This request key was used for different intake data.", 409)
        return db.get(SourceItem, prior.source_id), prior.source_revision
    prior_source = db.scalar(select(SourceItem).where(SourceItem.school_id == school_id, SourceItem.external_scope == metadata.external_scope, SourceItem.external_id == metadata.external_id))
    if replace_id:
        row = source(db, actor, school_id, replace_id, lock=True)
        check_version(row, expected_version)
        if prior_source is None or prior_source.id != row.id:
            raise DomainError("source_identity_conflict", "A new source revision must retain the source identity.", 409)
        revision = row.current_revision + 1
        row.current_revision = revision
        row.state = "received"
        row.sender = metadata.sender
        row.document_type = metadata.document_type
        row.received_at = metadata.received_at
        row.original_at = metadata.original_at
    elif prior_source:
        old = source_revision(db, school_id, prior_source.id, prior_source.current_revision)
        # Source identity is stable. Different bytes require an explicit revision command.
        if old.digest != digest:
            raise DomainError("source_identity_conflict", "This source identity has different content. Add an explicit revision.", 409)
        db.add(IntakeCommand(school_id=school_id, request_key=metadata.request_key, request_digest=command_digest, source_id=prior_source.id, source_revision=old.revision))
        db.flush()
        return prior_source, old.revision
    else:
        row = SourceItem(school_id=school_id, external_scope=metadata.external_scope, external_id=metadata.external_id, sender=metadata.sender, document_type=metadata.document_type, received_at=metadata.received_at, original_at=metadata.original_at, state="received")
        db.add(row)
        db.flush()
        revision = 1
    key = str(uuid4())
    storage.put(key, content)
    # The router removes this object if the database transaction fails; no orphaned
    # original is ever exposed through HTTP. Services expose keys for caller cleanup.
    db.info.setdefault("evidence_new_objects", []).append((storage, key))
    db.add(SourceRevision(school_id=school_id, source_id=row.id, revision=revision, digest=digest, sender=metadata.sender, document_type=metadata.document_type, received_at=metadata.received_at, original_at=metadata.original_at, filename=filename, media_type=media_type, storage_key=key, byte_size=len(content)))
    db.flush()
    inspected = Inspection(school_id=school_id, source_id=row.id, source_revision=revision, state="received")
    db.add(inspected)
    db.add(IntakeCommand(school_id=school_id, request_key=metadata.request_key, request_digest=command_digest, source_id=row.id, source_revision=revision))
    db.flush()
    process(db, row, inspected, content, extension, scanner, ocr, note=note)
    event(db, actor, school_id, "source.received", row, source_revision=revision)
    return row, revision


def process(db, row, inspected, content, extension, scanner, ocr, *, note=False):
    inspected.pages = []
    inspected.issue = None
    row.state = "processing"
    try:
        if note:
            inspected.scan_state = "not_required_note"
        elif scanner is None:
            raise ProcessingUnavailable("scanner_unavailable")
        else:
            result = scanner.scan(content)
            inspected.scan_state = result if result in {"clean", "infected"} else "unavailable"
            if result == "infected":
                raise UnsafeFile("malware_detected")
            if result != "clean":
                raise ProcessingUnavailable("scanner_unavailable")
        pages = bounded_extract(content, extension, scanner, ocr)
        inspected.pages = pages
        inspected.extraction_state = "ready"
        inspected.state = "ready"
        row.state = "needs_review"
        proposal_count = 0
        for page_number, page in enumerate(pages, 1):
            # Deterministic literal proposals. There is no instruction interpreter,
            # inferred learner identity, remote service or authoritative mutation.
            offset = 0
            for paragraph in page.splitlines(keepends=True):
                value = paragraph.strip()
                start = offset + len(paragraph) - len(paragraph.lstrip())
                end = start + len(value)
                if value and len(value) <= 20000 and proposal_count < 500:
                    proposal_count += 1
                    existing = db.scalar(select(ExtractionProposal.id).where(ExtractionProposal.school_id == row.school_id, ExtractionProposal.source_id == row.id, ExtractionProposal.source_revision == inspected.source_revision, ExtractionProposal.page == page_number, ExtractionProposal.span_start == start, ExtractionProposal.span_end == end, ExtractionProposal.field_name == "content"))
                    if existing is None:
                        db.add(ExtractionProposal(school_id=row.school_id, source_id=row.id, source_revision=inspected.source_revision, page=page_number, span_start=start, span_end=end, field_name="content", proposed_value=value))
                elif value and proposal_count >= 500:
                    inspected.issue = "proposal_limit_manual_fields"
                offset += len(paragraph)
    except ProcessingUnavailable as exc:
        code = str(exc)
        if inspected.scan_state == "pending":
            inspected.scan_state = "unavailable"
        inspected.extraction_state = "unavailable"
        inspected.issue = code if code in {"scanner_unavailable", "ocr_unavailable", "ocr_failed", "plain_text_email_required", "manual_transcription_required"} else "processing_unavailable"
        inspected.state = row.state = "needs_clarification" if inspected.scan_state in {"clean", "not_required_note"} else "quarantined"
    except Exception:
        # Parsing errors and dangerous archives never echo parser text/pupil data.
        inspected.extraction_state = "rejected"
        inspected.issue = "unsafe_or_invalid_document"
        inspected.state = row.state = "quarantined"


def read_original(storage, revision):
    try:
        content = storage.read(revision.storage_key)
    except OSError:
        raise DomainError("source_storage_unavailable", "The preserved original is temporarily unavailable.", 503) from None
    if hashlib.sha256(content).hexdigest() != revision.digest:
        raise DomainError("source_integrity", "The preserved original failed its integrity check.", 409)
    return content


def reprocess(db, actor, school_id, source_id, expected_version, storage, scanner, ocr):
    row = source(db, actor, school_id, source_id, lock=True)
    check_version(row, expected_version)
    inspected = inspection(db, row)
    if inspected.extraction_state == "ready":
        raise conflict("This revision is already extracted. Add a new source revision to change its text.")
    revision = source_revision(db, school_id, row.id, row.current_revision)
    content = read_original(storage, revision)
    process(db, row, inspected, content, Path(revision.filename).suffix.lower(), scanner, ocr, note=inspected.scan_state == "not_required_note")
    # A retry must increment source version even when it retains its previous status.
    row.updated_at = utcnow()
    event(db, actor, school_id, "source.inspected", row)
    return row


def span(db, row, revision, page, start, end):
    inspected = inspection(db, row, revision)
    if inspected is None or inspected.extraction_state != "ready" or inspected.scan_state not in {"clean", "not_required_note"}:
        raise DomainError("source_not_ready", "The source requires scanning or manual clarification.", 409)
    if page < 1 or page > len(inspected.pages) or start < 0 or end <= start or end > len(inspected.pages[page - 1]):
        raise DomainError("source_span", "Select an exact span within a source page.", 422)
    return inspected.pages[page - 1][start:end]


def review_progress(db, row, revision=None):
    fields = db.scalars(select(ExtractionProposal).where(ExtractionProposal.school_id == row.school_id, ExtractionProposal.source_id == row.id, ExtractionProposal.source_revision == (revision or row.current_revision))).all()
    counts = {"pending": 0, "reviewed_unconfirmed": 0, "confirmed": 0, "rejected": 0}
    for field in fields:
        if field.outcome == "rejected":
            counts["rejected"] += 1
        elif field.state == "confirmed":
            counts["confirmed"] += 1
        elif field.outcome in {"accepted", "edited"}:
            counts["reviewed_unconfirmed"] += 1
        else:
            counts["pending"] += 1
    return counts


def update_intake_completion(db, row):
    # The source row is locked by the caller. A reviewed interpretation is not a
    # release to a pupil; accepted/edited fields still require confirmation.
    counts = review_progress(db, row)
    if counts["pending"]:
        row.state = "needs_review"
    elif counts["reviewed_unconfirmed"]:
        row.state = "awaiting_confirmation"
    elif counts["confirmed"] or counts["rejected"]:
        row.state = "done"
    else:
        row.state = "needs_clarification"
    return counts


def propose(db, actor, school_id, source_id, command):
    row = source(db, actor, school_id, source_id, lock=True)
    check_version(row, command.expected_version)
    span(db, row, row.current_revision, command.page, command.span_start, command.span_end)
    existing = db.scalar(select(ExtractionProposal).where(ExtractionProposal.school_id == school_id, ExtractionProposal.source_id == row.id, ExtractionProposal.source_revision == row.current_revision, ExtractionProposal.page == command.page, ExtractionProposal.span_start == command.span_start, ExtractionProposal.span_end == command.span_end, ExtractionProposal.field_name == command.field_name))
    if existing:
        if existing.proposed_value != command.proposed_value:
            raise conflict("A different proposal already uses this source field and span.")
        return existing
    proposal = ExtractionProposal(school_id=school_id, source_id=row.id, source_revision=row.current_revision, **command.model_dump(exclude={"expected_version"}))
    db.add(proposal)
    update_intake_completion(db, row)
    row.updated_at = utcnow()
    event(db, actor, school_id, "source.field_proposed", row)
    return proposal


def get_proposal(db, actor, school_id, proposal_id):
    intake_access(db, actor, school_id)
    proposal = db.scalar(select(ExtractionProposal).where(ExtractionProposal.id == proposal_id, ExtractionProposal.school_id == school_id))
    if proposal is None:
        raise access_denied()
    return proposal


def review(db, actor, school_id, proposal_id, command):
    proposal = get_proposal(db, actor, school_id, proposal_id)
    check_version(proposal, command.expected_version)
    if proposal.outcome != "pending":
        raise conflict("This field has already been reviewed.")
    row = source(db, actor, school_id, proposal.source_id, lock=True)
    if proposal.source_revision != row.current_revision:
        raise conflict("A newer source revision requires a fresh review.")
    value = command.value if command.outcome == "edited" else proposal.proposed_value
    try:
        validate_field(proposal.field_name, value)
    except ValueError:
        raise DomainError("field_value", "The edited value does not match the field type.", 422) from None
    proposal.outcome = command.outcome
    proposal.state = "rejected" if command.outcome == "rejected" else "reviewed"
    proposal.reviewed_value = value if command.outcome != "rejected" else None
    proposal.review_reason = command.reason
    proposal.reviewer_id = actor.user_id
    update_intake_completion(db, row)
    event(db, actor, school_id, "source.field_reviewed", proposal)
    return proposal


def new_link(db, item, revision, excerpt, page, start, end):
    link = SourceSubjectLink(school_id=item.school_id, evidence_id=item.id, learner_id=item.learner_id, source_id=revision.source_id, source_revision=revision.revision, source_digest=revision.digest, page=page, span_start=start, span_end=end, excerpt=excerpt)
    db.add(link)
    db.flush()
    return link


def attribution(command):
    fields = command.model_dump(exclude={"expected_version", "excerpt_page", "excerpt_start", "excerpt_end", "content", "reason"})
    fields["learner_id"] = str(command.learner_id)
    fields["goal_revision_id"] = str(command.goal_revision_id) if command.goal_revision_id else None
    return fields


def confirm(db, actor, school_id, proposal_id, command, goal_validator=None):
    proposal = get_proposal(db, actor, school_id, proposal_id)
    require_learner_access(db, actor, school_id, str(command.learner_id), "evidence.write")
    check_version(proposal, command.expected_version)
    row = source(db, actor, school_id, proposal.source_id, lock=True)
    if proposal.source_revision != row.current_revision or proposal.outcome not in {"accepted", "edited"}:
        raise conflict("Confirm only a reviewed field from the current source revision.")
    if command.goal_revision_id is not None:
        if goal_validator is None:
            raise DomainError("goal_validation_unavailable", "Goal scope validation is not configured.", 503)
        goal_validator(db, actor, school_id, str(command.learner_id), str(command.goal_revision_id))
    if command.occurred_at > utcnow():
        raise DomainError("occurrence_future", "Confirmed evidence requires an occurrence in the past.", 422)
    if (command.excerpt_page != proposal.page or command.excerpt_start > proposal.span_start or command.excerpt_end < proposal.span_end):
        raise DomainError("excerpt_scope", "The controlled excerpt must contain the field's exact source span.", 422)
    excerpt = span(db, row, proposal.source_revision, command.excerpt_page, command.excerpt_start, command.excerpt_end)
    if len(excerpt) > 20000:
        raise DomainError("excerpt_size", "Choose a smaller learner-specific excerpt.", 422)
    existing = db.scalar(select(EvidenceItem).where(EvidenceItem.school_id == school_id, EvidenceItem.proposal_id == proposal.id))
    if existing:
        raise conflict("This field has already been confirmed. Use its correction command.")
    item = EvidenceItem(school_id=school_id, learner_id=str(command.learner_id), proposal_id=proposal.id)
    db.add(item)
    db.flush()
    revision = source_revision(db, school_id, row.id, proposal.source_revision)
    link = new_link(db, item, revision, excerpt, command.excerpt_page, command.excerpt_start, command.excerpt_end)
    db.add(EvidenceRevision(school_id=school_id, evidence_id=item.id, revision=1, link_id=link.id, content=proposal.reviewed_value, field_name=proposal.field_name, recorded_by=actor.user_id, **attribution(command)))
    proposal.state = "confirmed"
    event(db, actor, school_id, "evidence.confirmed", item, learner_id=item.learner_id)
    update_intake_completion(db, row)
    return item


def evidence(db, actor, school_id, evidence_id, action="evidence.read", *, lock=False):
    statement = select(EvidenceItem).where(EvidenceItem.school_id == school_id, EvidenceItem.id == evidence_id)
    if lock:
        statement = statement.with_for_update()
    item = db.scalar(statement)
    if item is None:
        raise access_denied()
    require_learner_access(db, actor, school_id, item.learner_id, action)
    return item


def current(db, item):
    return db.scalar(select(EvidenceRevision).where(EvidenceRevision.school_id == item.school_id, EvidenceRevision.evidence_id == item.id, EvidenceRevision.revision == item.current_revision))


def evidence_view(db, item):
    revision = current(db, item)
    link = db.get(SourceSubjectLink, revision.link_id)
    return {"id": item.id, "learner_id": item.learner_id, "version": item.version, "revision": revision.revision, "state": item.state, "content": revision.content, "field_name": revision.field_name, "claim_type": revision.claim_type, "source_type": revision.source_type, "reporter": revision.reporter, "observer": revision.observer, "certainty": revision.certainty, "occurred_at": revision.occurred_at, "recorded_at": revision.recorded_at, "topic": revision.topic, "goal_revision_id": revision.goal_revision_id, "source": {"link_id": link.id, "source_id": link.source_id, "revision": link.source_revision, "digest": link.source_digest, "page": link.page, "span_start": link.span_start, "span_end": link.span_end}}


def excerpt_view(db, actor, school_id, link_id):
    link = db.scalar(select(SourceSubjectLink).where(SourceSubjectLink.school_id == school_id, SourceSubjectLink.id == link_id, SourceSubjectLink.revoked_at.is_(None)))
    if link is None:
        raise access_denied()
    item = evidence(db, actor, school_id, link.evidence_id)
    if link.learner_id != item.learner_id or current(db, item).link_id != link.id:
        raise access_denied()
    return {"excerpt": link.excerpt, "source_id": link.source_id, "revision": link.source_revision, "digest": link.source_digest, "page": link.page, "span_start": link.span_start, "span_end": link.span_end}


def correct(db, actor, school_id, evidence_id, command, goal_validator=None):
    item = evidence(db, actor, school_id, evidence_id, "evidence.write", lock=True)
    check_version(item, command.expected_version)
    require_learner_access(db, actor, school_id, str(command.learner_id), "evidence.write")
    if command.goal_revision_id is not None:
        if goal_validator is None:
            raise DomainError("goal_validation_unavailable", "Goal scope validation is not configured.", 503)
        goal_validator(db, actor, school_id, str(command.learner_id), str(command.goal_revision_id))
    if command.occurred_at > utcnow():
        raise DomainError("occurrence_future", "Confirmed evidence requires an occurrence in the past.", 422)
    previous = current(db, item)
    try:
        validate_field(previous.field_name, command.content)
    except ValueError:
        raise DomainError("field_value", "Correction does not match the field type.", 422) from None
    reassigned = item.learner_id != str(command.learner_id)
    old_link = db.get(SourceSubjectLink, previous.link_id)
    if reassigned:
        intake_access(db, actor, school_id)
        if command.excerpt_page is None:
            raise DomainError("excerpt_review_required", "Select and review the exact excerpt for the corrected pupil association.", 422)
    if command.excerpt_page is not None:
        page, start, end = command.excerpt_page, command.excerpt_start, command.excerpt_end
        # A pupil team may retract/narrow its released text. Access to any other
        # original text still requires the independent restricted intake authority.
        if page != old_link.page or start < old_link.span_start or end > old_link.span_end:
            intake_access(db, actor, school_id)
    else:
        proposal = db.get(ExtractionProposal, item.proposal_id)
        page, start, end = old_link.page, old_link.span_start, old_link.span_end
        # Safe compatibility default: strip incidental surrounding text to the
        # originally reviewed field, and never widen an already corrected span.
        if proposal.page == page:
            overlap_start, overlap_end = max(start, proposal.span_start), min(end, proposal.span_end)
            if overlap_start < overlap_end:
                start, end = overlap_start, overlap_end
    revision = source_revision(db, school_id, old_link.source_id, old_link.source_revision)
    source_row = db.get(SourceItem, old_link.source_id)
    excerpt = span(db, source_row, revision.revision, page, start, end)
    if len(excerpt) > 20000:
        raise DomainError("excerpt_size", "Choose a smaller learner-specific excerpt.", 422)
    old_learner = item.learner_id
    old_revision = item.current_revision
    old_link.revoked_at = utcnow()
    item.learner_id = str(command.learner_id)
    item.current_revision += 1
    link = new_link(db, item, revision, excerpt, page, start, end)
    db.add(EvidenceRevision(school_id=school_id, evidence_id=item.id, revision=item.current_revision, link_id=link.id, content=command.content, field_name=previous.field_name, correction_reason=command.reason, recorded_by=actor.user_id, **attribution(command)))
    for derivative in db.scalars(select(Derivative).where(Derivative.school_id == school_id, Derivative.evidence_id == item.id, Derivative.state.in_(["draft", "shared"]))):
        derivative.state = "shared_review_required" if derivative.state == "shared" else "stale"
        db.add(CorrectionImpact(school_id=school_id, evidence_id=item.id, old_revision=old_revision, new_revision=item.current_revision, derivative_id=derivative.id, disposition=derivative.state))
    event(db, actor, school_id, "evidence.corrected", item, old_learner_id=old_learner, learner_id=item.learner_id, old_revision=old_revision, new_revision=item.current_revision)
    return item


def register_derivative(db, actor, school_id, evidence_id, command):
    item = evidence(db, actor, school_id, evidence_id, "evidence.write", lock=True)
    if command.evidence_revision != item.current_revision:
        raise conflict("Only the current evidence revision may support a new derivative.")
    values = command.model_dump(mode="json")
    prior = db.scalar(select(Derivative).where(Derivative.school_id == school_id, Derivative.evidence_id == item.id, Derivative.evidence_revision == command.evidence_revision, Derivative.target_type == command.target_type, Derivative.target_id == str(command.target_id), Derivative.target_revision == command.target_revision))
    if prior:
        if prior.state != command.state:
            raise conflict("The derivative is already registered with another state.")
        return prior
    row = Derivative(school_id=school_id, learner_id=item.learner_id, evidence_id=item.id, **values)
    db.add(row)
    event(db, actor, school_id, "evidence.derivative_registered", row)
    return row


def timeline(db, actor, school_id, learner_id, *, date_basis="occurred", start=None, end=None, topic=None, goal_revision_id=None, source_id=None, document_type=None, query=None, certainty=None, offset=0, limit=50):
    require_learner_access(db, actor, school_id, learner_id, "evidence.read")
    filters = [EvidenceItem.school_id == school_id, EvidenceItem.learner_id == learner_id, EvidenceRevision.revision == EvidenceItem.current_revision]
    time = EvidenceRevision.occurred_at if date_basis == "occurred" else EvidenceRevision.recorded_at
    if start:
        filters.append(time >= start)
    if end:
        filters.append(time < end)
    if start and end and start >= end:
        raise DomainError("period", "The interval end must follow its start.", 422)
    for column, value in ((EvidenceRevision.topic, topic), (EvidenceRevision.goal_revision_id, goal_revision_id), (SourceSubjectLink.source_id, source_id), (SourceRevision.document_type, document_type), (EvidenceRevision.certainty, certainty)):
        if value is not None:
            filters.append(column == str(value))
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(EvidenceRevision.content.ilike("%" + escaped + "%", escape="\\"))
    statement = select(EvidenceItem).join(EvidenceRevision, (EvidenceRevision.evidence_id == EvidenceItem.id) & (EvidenceRevision.school_id == EvidenceItem.school_id)).join(SourceSubjectLink, SourceSubjectLink.id == EvidenceRevision.link_id).join(SourceRevision, (SourceRevision.source_id == SourceSubjectLink.source_id) & (SourceRevision.school_id == SourceSubjectLink.school_id) & (SourceRevision.revision == SourceSubjectLink.source_revision)).where(*filters)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(time.desc(), EvidenceItem.id).offset(offset).limit(limit)).all()
    return {"items": [evidence_view(db, row) for row in rows], "total": total}
