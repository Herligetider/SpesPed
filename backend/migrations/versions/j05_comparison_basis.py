"""Retain exact expert-parent and provision provenance on comparison clarifications."""
from copy import deepcopy
from uuid import UUID
from alembic import op
import sqlalchemy as sa

revision = 'j05_comparison_basis'
down_revision = 'j05_plans'
branch_labels = None
depends_on = None


def valid_id(value):
    try:
        return isinstance(value,str) and UUID(value).int != 0
    except (ValueError,TypeError,AttributeError):
        return False


def valid_source(value):
    return (isinstance(value,dict) and set(value) == {'evidence_id','evidence_revision','link_id'}
            and valid_id(value['evidence_id']) and valid_id(value['link_id'])
            and type(value['evidence_revision']) is int and value['evidence_revision'] >= 1)


def upgrade():
    op.add_column('entitlements_case_clarifications',sa.Column('comparison_basis',sa.JSON(),nullable=True))
    db=op.get_bind()
    issues=sa.table('entitlements_case_clarifications',sa.column('id',sa.String()),sa.column('school_id',sa.String()),sa.column('learner_id',sa.String()),sa.column('case_id',sa.String()),sa.column('kind',sa.String()),sa.column('source',sa.JSON()),sa.column('reference_id',sa.String()),sa.column('comparison_basis',sa.JSON()))
    events=sa.table('entitlements_outbox',sa.column('school_id',sa.String()),sa.column('aggregate_id',sa.String()),sa.column('event_type',sa.String()),sa.column('payload',sa.JSON()))
    recommendations=sa.table('entitlements_recommendations',sa.column('id',sa.String()),sa.column('school_id',sa.String()),sa.column('assessment_id',sa.String()),sa.column('category',sa.String()),sa.column('subject',sa.String()),sa.column('source',sa.JSON()))
    assessments=sa.table('entitlements_expert_assessments',sa.column('id',sa.String()),sa.column('school_id',sa.String()),sa.column('learner_id',sa.String()),sa.column('case_id',sa.String()),sa.column('confirmed_by',sa.String()),sa.column('source',sa.JSON()))
    decisions=sa.table('entitlements_education_decisions',sa.column('id',sa.String()),sa.column('school_id',sa.String()),sa.column('learner_id',sa.String()),sa.column('case_id',sa.String()))
    revisions=sa.table('entitlements_decision_revisions',sa.column('id',sa.String()),sa.column('school_id',sa.String()),sa.column('decision_id',sa.String()),sa.column('confirmed_by',sa.String()),sa.column('source',sa.JSON()))
    provisions=sa.table('entitlements_decision_provisions',sa.column('id',sa.String()),sa.column('school_id',sa.String()),sa.column('decision_revision_id',sa.String()),sa.column('category',sa.String()),sa.column('subject',sa.String()),sa.column('source',sa.JSON()))
    for issue in db.execute(sa.select(issues).where(issues.c.kind == 'recommendation_difference',issues.c.reference_id.is_not(None))).mappings().all():
        # An exact retained event identifies the originating recommendation. Do
        # not infer it from matching text, dates or other assessments in this case.
        retained=db.execute(sa.select(events.c.payload).where(events.c.school_id == issue['school_id'],events.c.aggregate_id == issue['id'],events.c.event_type == 'support_case.recommendation_difference')).scalars().all()
        if len(retained) != 1 or not isinstance(retained[0],dict):
            continue
        payload=retained[0]
        recommendation_id=payload.get('recommendation_id')
        if not valid_id(recommendation_id) or payload.get('decision_revision_id') != issue['reference_id']:
            continue
        rec=db.execute(sa.select(recommendations).where(recommendations.c.school_id == issue['school_id'],recommendations.c.id == recommendation_id)).mappings().first()
        if rec is None or rec['source'] != issue['source']:
            continue
        assessment=db.execute(sa.select(assessments).where(assessments.c.school_id == issue['school_id'],assessments.c.id == rec['assessment_id'],assessments.c.learner_id == issue['learner_id'],assessments.c.case_id == issue['case_id'],assessments.c.confirmed_by.is_not(None))).mappings().first()
        rev=db.execute(sa.select(revisions).where(revisions.c.school_id == issue['school_id'],revisions.c.id == issue['reference_id'],revisions.c.confirmed_by.is_not(None))).mappings().first()
        if assessment is None or rev is None:
            continue
        decision=db.execute(sa.select(decisions).where(decisions.c.school_id == issue['school_id'],decisions.c.id == rev['decision_id'],decisions.c.learner_id == issue['learner_id'],decisions.c.case_id == issue['case_id'])).mappings().first()
        if decision is None:
            continue
        compared=db.execute(sa.select(provisions).where(provisions.c.school_id == issue['school_id'],provisions.c.decision_revision_id == rev['id'],provisions.c.category == rec['category'],provisions.c.subject == rec['subject']).order_by(provisions.c.id)).mappings().all()
        bindings=[assessment['source'],rec['source'],rev['source'],*[p['source'] for p in compared]]
        if not all(valid_source(source) for source in bindings):
            continue
        basis=deepcopy({'format':'spesped.recommendation_comparison.v1','assessment_id':assessment['id'],'assessment_source':assessment['source'],'recommendation_id':rec['id'],'recommendation_source':rec['source'],'decision_id':decision['id'],'decision_revision_id':rev['id'],'decision_source':rev['source'],'provisions':[{'provision_id':p['id'],'source':p['source']} for p in compared]})
        # Retained history is untouched. Unknown/ambiguous provenance stays NULL;
        # the application fails closed and requires clarification in that case.
        db.execute(sa.update(issues).where(issues.c.school_id == issue['school_id'],issues.c.id == issue['id']).values(comparison_basis=basis))


def downgrade():
    op.drop_column('entitlements_case_clarifications','comparison_basis')
