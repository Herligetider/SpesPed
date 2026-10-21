"""Metadata-only currency for previously authorized curated decision bindings."""
from sqlalchemy import select
from spesped.contexts.evidence.projections import confirmed_binding_is_current
from .models import EducationDecision, DecisionRevision, DecisionProvision, SupportCase


def provision_binding_is_current(db, school_id, learner_id, binding, at, *, historical=False):
    """No source prose, case metadata or permission is returned by this predicate."""
    try:
        decision = db.execute(select(EducationDecision.id,EducationDecision.case_id,EducationDecision.current_revision,EducationDecision.state).where(EducationDecision.school_id == school_id, EducationDecision.learner_id == learner_id, EducationDecision.id == str(binding['decision_id'])).execution_options(populate_existing=True)).first()
        if decision is None: return False
        case = db.execute(select(SupportCase.id).where(SupportCase.school_id == school_id,SupportCase.learner_id == learner_id,SupportCase.id == decision.case_id).execution_options(populate_existing=True)).first()
        revision = db.execute(select(DecisionRevision.id,DecisionRevision.revision,DecisionRevision.confirmed_by,DecisionRevision.state,DecisionRevision.effective_from,DecisionRevision.effective_until,DecisionRevision.source).where(DecisionRevision.school_id == school_id,DecisionRevision.decision_id == decision.id,DecisionRevision.id == str(binding['decision_revision_id'])).execution_options(populate_existing=True)).first()
        provision = db.execute(select(DecisionProvision.id,DecisionProvision.effective_from,DecisionProvision.effective_until,DecisionProvision.source).where(DecisionProvision.school_id == school_id,DecisionProvision.decision_revision_id == str(binding['decision_revision_id']),DecisionProvision.id == str(binding['provision_id'])).execution_options(populate_existing=True)).first()
        if case is None or revision is None or provision is None or revision.confirmed_by is None or revision.state not in {'confirmed','superseded'}: return False
        if not historical and (decision.current_revision != revision.revision or decision.state != 'confirmed'): return False
        if not (revision.effective_from <= at < revision.effective_until and provision.effective_from <= at < provision.effective_until): return False
        for source in (revision.source,provision.source):
            if not confirmed_binding_is_current(db,school_id,learner_id,str(source['evidence_id']),source['evidence_revision'],str(source['link_id'])): return False
        return True
    except (KeyError,TypeError,ValueError):
        return False
