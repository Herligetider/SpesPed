"""Exact immutable provenance for an individual expert/decision comparison."""
from copy import deepcopy
from uuid import UUID
from sqlalchemy import select
from .models import ExpertAssessment, Recommendation, EducationDecision, DecisionRevision, DecisionProvision

FORMAT = 'spesped.recommendation_comparison.v1'


def valid_id(value):
    try:
        return isinstance(value,str) and UUID(value).int != 0
    except (ValueError,TypeError,AttributeError):
        return False


def valid_binding(value):
    return (isinstance(value,dict) and set(value) == {'evidence_id','evidence_revision','link_id'}
            and valid_id(value['evidence_id']) and valid_id(value['link_id'])
            and type(value['evidence_revision']) is int and value['evidence_revision'] >= 1)


def comparison_basis(assessment, recommendation, decision, revision, provisions):
    """Freeze only the sources actually compared, never later case material."""
    return deepcopy({
        'format': FORMAT,
        'assessment_id': assessment.id,
        'assessment_source': assessment.source,
        'recommendation_id': recommendation.id,
        'recommendation_source': recommendation.source,
        'decision_id': decision.id,
        'decision_revision_id': revision.id,
        'decision_source': revision.source,
        'provisions': [{'provision_id': p.id, 'source': p.source} for p in sorted(provisions, key=lambda p: p.id)],
    })


def comparison_bindings(db, clarification):
    """Resolve recorded identities within their original case, or fail closed.

    This returns binding metadata only. It confers no source-prose permission;
    every caller must still authorize the case and use actor-aware evidence checks.
    Unknown legacy lineage cannot be replaced by a guess from nearby assessments.
    """
    basis = clarification.comparison_basis
    required = {'format', 'assessment_id', 'assessment_source', 'recommendation_id',
                'recommendation_source', 'decision_id', 'decision_revision_id', 'decision_source', 'provisions'}
    if not isinstance(basis, dict) or set(basis) != required or basis['format'] != FORMAT:
        return None
    if (not all(valid_id(basis[name]) for name in ('assessment_id','recommendation_id','decision_id','decision_revision_id'))
            or not all(valid_binding(basis[name]) for name in ('assessment_source','recommendation_source','decision_source'))
            or not isinstance(basis['provisions'], list)):
        return None
    assessment = db.scalar(select(ExpertAssessment).where(
        ExpertAssessment.school_id == clarification.school_id,
        ExpertAssessment.learner_id == clarification.learner_id,
        ExpertAssessment.case_id == clarification.case_id,
        ExpertAssessment.id == basis['assessment_id']))
    if assessment is None or assessment.confirmed_by is None:
        return None
    recommendation = db.scalar(select(Recommendation).where(
        Recommendation.school_id == clarification.school_id,
        Recommendation.assessment_id == assessment.id,
        Recommendation.id == basis['recommendation_id']))
    decision = db.scalar(select(EducationDecision).where(
        EducationDecision.school_id == clarification.school_id,
        EducationDecision.learner_id == clarification.learner_id,
        EducationDecision.case_id == clarification.case_id,
        EducationDecision.id == basis['decision_id']))
    if recommendation is None or decision is None:
        return None
    revision = db.scalar(select(DecisionRevision).where(
        DecisionRevision.school_id == clarification.school_id,
        DecisionRevision.decision_id == decision.id,
        DecisionRevision.id == basis['decision_revision_id']))
    if revision is None or revision.confirmed_by is None or revision.id != clarification.reference_id:
        return None
    if (basis['assessment_source'] != assessment.source
            or basis['recommendation_source'] != recommendation.source
            or basis['recommendation_source'] != clarification.source
            or basis['decision_source'] != revision.source):
        return None
    bindings = [basis['assessment_source'], basis['recommendation_source'], basis['decision_source']]
    seen = set()
    for entry in basis['provisions']:
        if not isinstance(entry, dict) or set(entry) != {'provision_id', 'source'} or not valid_id(entry['provision_id']) or not valid_binding(entry['source']) or entry['provision_id'] in seen:
            return None
        seen.add(entry['provision_id'])
        provision = db.scalar(select(DecisionProvision).where(
            DecisionProvision.school_id == clarification.school_id,
            DecisionProvision.decision_revision_id == revision.id,
            DecisionProvision.id == entry['provision_id'],
            DecisionProvision.category == recommendation.category,
            DecisionProvision.subject == recommendation.subject))
        if provision is None or provision.source != entry['source']:
            return None
        bindings.append(entry['source'])
    return bindings
