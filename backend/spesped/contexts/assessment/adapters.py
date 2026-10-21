"""Production source reads use authenticated owning services, never supplied prose."""
import json
from contextlib import contextmanager
from functools import wraps
from sqlalchemy.orm import Session
from spesped.errors import DomainError,access_denied
from spesped.contexts.curriculum.adapters import digest,canonical

@contextmanager
def owner_reader(db):
    """Fresh identities over the same transaction, without changing caller objects.

    rollback_only joins an already-begun Connection transaction: close neither
    commits nor rolls it back. The owner services used here are strictly reads.
    """
    watched=('spesped.contexts.identity.','spesped.contexts.evidence.','spesped.contexts.plans.','spesped.contexts.teaching.','spesped.contexts.curriculum.','spesped.contexts.entitlements.','spesped.contexts.platform.')
    if any(type(row).__module__.startswith(watched) for row in db.new|db.dirty|db.deleted):
        raise DomainError('dependency_pending','Flush or roll back pending source or permission changes before resolving assessment content.',409)
    with db.no_autoflush:
        reader=Session(bind=db.connection(),join_transaction_mode='rollback_only',autoflush=False,expire_on_commit=False)
        reader.info.update(db.info)
        try:yield reader
        finally:reader.close()

def school_sources(db,actor,school_id,refs,purpose='read'):
    from spesped.contexts.curriculum.service import sources
    with owner_reader(db) as reader:return [v.model_dump(mode='json') for v in sources(reader,actor,school_id,refs,purpose)]

def goal(db,actor,school_id,learner_id,goal_id,at):
    from spesped.contexts.plans.projections import teaching_goal_basis
    with owner_reader(db) as reader:return json.loads(canonical(teaching_goal_basis(reader,actor,school_id,learner_id,str(goal_id),at=at,historical=True)))

def scheme(db,actor,school_id,revision_id,starts_on,ends_on):
    if revision_id is None:return None
    from spesped.contexts.curriculum.projections import reviewed_assessment_scheme
    with owner_reader(db) as reader:return json.loads(canonical(reviewed_assessment_scheme(reader,actor,school_id,str(revision_id),starts_on=starts_on,ends_on=ends_on)))

def actual(db,actor,school_id,learner_id,revision_id):
    from spesped.contexts.teaching.projections import learner_delivery_basis
    with owner_reader(db) as reader:return json.loads(canonical(learner_delivery_basis(reader,actor,school_id,learner_id,str(revision_id))))

def observation(db,actor,school_id,learner_id,revision_id):
    from spesped.contexts.teaching.service import read_observation
    with owner_reader(db) as reader:return json.loads(canonical(read_observation(reader,actor,school_id,learner_id,str(revision_id))))

def observations(db,actor,school_id,learner_id,goal_id,start,end):
    from spesped.contexts.teaching.service import observations_for_learner
    values=[];offset=0
    with owner_reader(db) as reader:
        while True:
            page=observations_for_learner(reader,actor,school_id,learner_id,start=start,end=end,goal_revision_id=str(goal_id),offset=offset,limit=100)
            values.extend(page['items']);offset+=len(page['items'])
            if offset>=page['total']:break
            if offset>=1000:raise DomainError('assessment_snapshot_limit','Narrow the period to at most 1000 observations.',422)
    return json.loads(canonical(values))

def evidence(db,actor,school_id,learner_id,ref):
    from spesped.contexts.evidence import service
    from spesped.contexts.evidence.projections import confirmed_binding_is_current
    with owner_reader(db) as reader:
        item=service.evidence(reader,actor,school_id,str(ref.id))
        if item.learner_id!=learner_id:raise access_denied()
        value=service.evidence_view(reader,item)
        if value['revision']!=ref.revision or value['source']['link_id']!=str(ref.link_id) or not confirmed_binding_is_current(reader,school_id,learner_id,str(ref.id),ref.revision,str(ref.link_id)):
            raise DomainError('assessment_source_changed','The exact confirmed evidence was corrected or withdrawn.',409)
        value['controlled_excerpt']=service.excerpt_view(reader,actor,school_id,str(ref.link_id))['excerpt']
        return json.loads(canonical(value))

def current_goal_binding(db,school_id,learner_id,binding,at):
    from spesped.contexts.plans.projections import goal_binding_is_current
    with owner_reader(db) as reader:return goal_binding_is_current(reader,school_id,learner_id,binding,at=at)

def goal_evidence(db,actor,school_id,learner_id,goal_id,start,end):
    from spesped.contexts.evidence.service import timeline
    from .schemas import EvidenceRef
    items=[];offset=0;unavailable=0
    with owner_reader(db) as reader:
        while True:
            page=timeline(reader,actor,school_id,learner_id,start=start,end=end,goal_revision_id=str(goal_id),offset=offset,limit=100)
            for value in page['items']:
                ref=EvidenceRef(kind='evidence',id=value['id'],revision=value['revision'],link_id=value['source']['link_id'])
                try:resolved=evidence(reader,actor,school_id,learner_id,ref)
                except DomainError as exc:
                    if exc.status_code in {403,409}:unavailable+=1;continue
                    raise
                items.append({'reference':ref.model_dump(mode='json'),'digest':digest(resolved),'value':resolved})
            offset+=len(page['items'])
            if offset>=page['total']:break
            if offset>=1000:raise DomainError('assessment_snapshot_limit','Narrow the period to at most 1000 goal evidence items.',422)
    return {'items':items,'unavailable_count':unavailable}
