"""Read through owning services over fresh identities on the caller transaction."""
import json
from contextlib import contextmanager
from datetime import datetime
from sqlalchemy.orm import Session
from spesped.errors import DomainError,access_denied
from spesped.contexts.curriculum.adapters import canonical,digest
from spesped.domain.primitives import SummaryPeriod
from . import schemas as s

@contextmanager
def owner_reader(db):
    # Refuse staged dependency edits before a refresh can overwrite them.
    excluded=('documents_commands','documents_outbox')
    if any(type(r).__module__.startswith('spesped.contexts.') and getattr(r,'__tablename__','') not in excluded for r in db.new|db.dirty|db.deleted):
        raise DomainError('dependency_pending','Flush or roll back staged source, identity or document changes before reading.',409)
    with db.no_autoflush:
        reader=Session(bind=db.connection(),join_transaction_mode='rollback_only',autoflush=False,expire_on_commit=False)
        reader.info.update(db.info)
        try:yield reader
        finally:reader.close()
def encode(v):return json.loads(canonical(v))
def period(db,school_id,starts_on,ends_on):
    from spesped.contexts.identity.models import School
    with db.no_autoflush:school=db.get(School,school_id)
    try:value=SummaryPeriod(starts_on,ends_on,school.timezone).to_utc()
    except ValueError:raise DomainError('document_period','Choose an ordered interval containing real calendar instants in the school timezone.',422) from None
    return value.start,value.end,school.timezone

def reference(db,actor,school_id,learner_id,ref):
    from spesped.contexts.assessment.service import resolve_reference
    with owner_reader(db) as reader:
        if ref.kind=='assessment_statement':
            from spesped.contexts.assessment import service as svc,models as m
            root=svc.get(reader,m.Statement,school_id,ref.id)
            if root.learner_id!=learner_id:raise access_denied()
            current=svc.statement_view(reader,actor,school_id,ref.id);revision=svc.statement_revision(reader,root)
            if current['state']!='finalized' or current['source_status']!='current' or not current['content'] or revision.number!=ref.revision:raise DomainError('statement_source_changed','Select an exact current human-finalized subject statement.',409)
            value={'statement_id':root.id,'subject':root.subject,'assessment_type':root.assessment_type,'revision_id':revision.id,'content':current['content'],'finalization':current['finalization'],'period':{'starts_on':root.starts_on,'ends_on':root.ends_on},'occurred_at':revision.created_at,'recorded_at':revision.created_at,'classification':'human_finalized_subject_statement'}
            value=encode(value)
            if ref.digest and digest(value)!=ref.digest:raise DomainError('statement_source_changed','The selected exact statement digest changed.',409)
            return {'reference':ref.model_dump(mode='json'),'value':value,'digest':digest(value)}
        return resolve_reference(reader,actor,school_id,learner_id,ref)

def observations(db,actor,school_id,learner_id,start,end):
    from spesped.contexts.teaching.service import observations_for_learner
    values=[];offset=0
    with owner_reader(db) as reader:
        while True:
            page=observations_for_learner(reader,actor,school_id,learner_id,start=start,end=end,offset=offset,limit=100)
            for v in page['items']:
                if v['confirmed'] and v['current']:values.append(v)
            offset+=len(page['items'])
            if offset>=page['total']:break
            if offset>=2000:raise DomainError('snapshot_limit','Narrow the interval to at most 2000 observations.',422)
    return encode(values)
def evidence(db,actor,school_id,learner_id,start,end):
    from spesped.contexts.evidence.service import timeline
    values=[];offset=0
    with owner_reader(db) as reader:
        while True:
            page=timeline(reader,actor,school_id,learner_id,start=start,end=end,offset=offset,limit=100)
            for v in page['items']:
                ref=s.EvidenceRef(kind='evidence',id=v['id'],revision=v['revision'],link_id=v['source']['link_id'])
                try:values.append(reference(reader,actor,school_id,learner_id,ref))
                except DomainError as exc:
                    if exc.status_code not in {403,409}:raise
                    # No unavailable source identity or prose escapes the owning scope.
            offset+=len(page['items'])
            if offset>=page['total']:break
            if offset>=2000:raise DomainError('snapshot_limit','Narrow the interval to at most 2000 evidence items.',422)
    return encode(values)
def goal(db,actor,school_id,learner_id,selected):
    from spesped.contexts.plans.projections import reporting_goal_basis
    with owner_reader(db) as reader:return encode(reporting_goal_basis(reader,actor,school_id,learner_id,str(selected.goal_revision_id),at=selected.applicable_at))
def actual(db,actor,school_id,learner_id,identity):
    from spesped.contexts.teaching.projections import learner_delivery_basis
    with owner_reader(db) as reader:return encode(learner_delivery_basis(reader,actor,school_id,learner_id,str(identity)))
def future_plan(db,actor,school_id,learner_id,identity):
    # The session owner checks the whole proposed plan and every permitted pupil.
    # BC10 accepts only a single-pupil plan: group prose is never copied.
    from spesped.contexts.teaching import service as svc,models as m
    with owner_reader(db) as reader:
        revision=svc.load(reader,m.SessionRevision,school_id,str(identity))
        row=svc.session(reader,actor,school_id,revision.session_id)
        basis=svc.load(reader,m.TeachingBasis,school_id,revision.basis_id)
        if len(basis.learners)!=1 or basis.learners[0]['learner_id']!=learner_id:raise access_denied()
        if svc.current_revision(reader,row).id!=revision.id:raise DomainError('future_plan_changed','The selected future plan was superseded.',409)
        view=svc.session_view(reader,actor,row,revision)
        if not svc.revision_valid(reader,actor,revision):raise DomainError('future_plan_changed','The selected future plan needs review.',409)
        return encode({'revision_id':revision.id,'planned_at':basis.planned_at,'content':view['content'],'classification':'future_plan_not_actual'})
def school_sources(db,actor,school_id,refs):
    from spesped.contexts.curriculum.service import sources
    with owner_reader(db) as reader:return encode(sources(reader,actor,school_id,refs,'read'))
def obligation(db,actor,school_id,learner_id,identity,kind,starts_on,ends_on):
    from spesped.contexts.governance import service as svc,models as m
    from spesped.contexts.governance.projections import _source_binding
    with owner_reader(db) as reader:
        task=svc.get_scoped(reader,m.ObligationInstance,school_id,str(identity));svc.task_access(reader,actor,task)
        if task.learner_id!=learner_id or task.case_id is not None:raise access_denied()
        binding,rule=_source_binding(reader,task)
        from dataclasses import asdict
        valid=(binding and binding.state=='current' and task.applicability=='applicable' and not task.unresolved_inputs and kind in rule.required_document_types and rule.valid_from<=starts_on and (rule.valid_until is None or ends_on<=rule.valid_until))
        return {'obligation_id':task.id,'requirement_version_id':task.requirement_version_id,'binding':asdict(binding) if binding else None,'state':'applicable' if valid else 'unresolved','unresolved_inputs':task.unresolved_inputs}
