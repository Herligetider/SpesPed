"""Exact reviewed assessment source inventory; source-native reads remain final."""
from sqlalchemy import select
from spesped.errors import DomainError
from spesped.contexts.identity.document_choices import reader, bounded
from . import models as m, service, schemas

def sources(db, actor, school_id, learner_id, start, end):
    with reader(db) as fresh:
        service.pupil_access(fresh, actor, school_id, learner_id)
        items = []
        specs = (
            ('assessment_result', m.ResultRevision, m.Administration, m.ResultRevision.administration_id,
                m.Administration.current_result, m.ResultRevision.occurred_at, 'professionally_reviewed'),
            ('progress_review', m.ProgressRevision, m.ProgressReview, m.ProgressRevision.review_id,
                m.ProgressReview.current_revision, m.ProgressRevision.created_at, 'confirmed'),
            ('assessment_statement', m.StatementRevision, m.Statement, m.StatementRevision.statement_id,
                m.Statement.current_revision, m.StatementRevision.created_at, 'finalized'),
        )
        for kind, revision, root, parent, current, occurred, state in specs:
            conditions = [root.school_id == school_id, root.learner_id == learner_id,
                revision.school_id == school_id, revision.number == current, root.state == state]
            if start is not None: conditions.append(occurred >= start)
            if end is not None: conditions.append(occurred < end)
            rows = bounded(fresh, select(revision, root).join(root, parent == root.id).where(*conditions).order_by(occurred, revision.id))
            for rev, row in rows:
                ref = dict(kind=kind, id=rev.id if kind == 'assessment_result' else row.id, revision=rev.number)
                try:
                    if kind == 'assessment_statement':
                        view = service.statement_view(fresh, actor, school_id, row.id)
                        if view['state'] != 'finalized' or view['source_status'] != 'current' or not view['content']: continue
                        label = f'{row.subject} — finalized subject statement'
                        current_state = 'current'
                    else:
                        value = service.resolve_reference(fresh, actor, school_id, learner_id, schemas.EvidenceRef.model_validate(ref))
                        ref = value['reference']
                        ref['digest'] = value['digest']
                        label = row.purpose[:200] if kind == 'assessment_result' else rev.finding['judgement'][:200]
                        current_state = 'review_required' if value['value'].get('source_review', {}).get('review_required') else 'current'
                except DomainError as exc:
                    if exc.status_code not in {403, 409}: raise
                    continue
                items.append(dict(reference=ref, label=label, source_type=kind,
                    occurred_at=rev.occurred_at if kind == 'assessment_result' else rev.created_at, state=current_state))
        return items
