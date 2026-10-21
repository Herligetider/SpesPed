"""BC04 application services. The caller owns commit/rollback."""
from sqlalchemy import select
from spesped.auth import Actor, active_at, school_today, require_authority, require_learner_access, require_school_access
from spesped.db import utcnow
from spesped.errors import DomainError, access_denied
from spesped.domain import (CaseId, CountingBasis, DecisionId, DecisionProvisionId, DecisionProvisionReference,
    EffectivePeriod, EntitlementQuantity, LearnerId, QuantityUnit, RevisionId, SchoolId, SubjectScope, SupportCategory,
    canonical_content_digest)
from spesped.contexts.identity.models import School, SchoolMembership
from .models import (SupportCase, EducationConsent, Referral, ReferralRevision, ReferralContact,
    ExpertAssessment, Recommendation, EducationDecision, DecisionRevision, DecisionProvision)
from .common import audit, conflict, depend, expected, replay, remember, source_binding, source_status, sources, touch


def case_access(db, actor, school_id, case_id, action='support_case.read', *, lock=False):
    membership = require_school_access(db, actor, school_id)
    if membership.role in {'guardian', 'technical_administrator'}:
        raise access_denied()
    query = select(SupportCase).where(SupportCase.school_id == school_id, SupportCase.id == case_id)
    if lock: query = query.with_for_update()
    row = db.scalar(query)
    if row is None or row.purpose != 'educational_support': raise access_denied()
    require_learner_access(db, actor, school_id, row.learner_id, 'support_case.access')
    require_authority(db, actor, school_id, action, learner_id=row.learner_id, case_id=row.id)
    return row


def child(db, actor, school_id, case_id, model, child_id, action='support_case.read', lock=False):
    case = case_access(db, actor, school_id, case_id, action, lock=lock)
    row = db.scalar(select(model).where(model.id == child_id, model.school_id == school_id, model.learner_id == case.learner_id, model.case_id == case.id))
    if row is None: raise access_denied()
    return case, row


def create_case(db, actor, school_id, learner_id, command):
    require_learner_access(db, actor, school_id, learner_id, 'support_case.create')
    require_authority(db, actor, school_id, 'support_case.create', learner_id=learner_id)
    prior, digest = replay(db, actor, school_id, 'case.create', command, learner_id)
    if prior: return db.get(SupportCase, prior)
    owner = db.scalar(select(SchoolMembership).where(SchoolMembership.school_id == school_id, SchoolMembership.user_id == str(command.owner_id), *active_at(SchoolMembership,school_today(db.get(School,school_id)))))
    if owner is None or owner.role in {'guardian','technical_administrator'}:
        raise DomainError('case_owner', 'Choose an active staff member in this school.', 422)
    require_learner_access(db, Actor(str(command.owner_id)), school_id, learner_id, 'support_case.access')
    row = SupportCase(school_id=school_id, learner_id=learner_id, concern=command.concern, purpose=command.purpose, owner_id=str(command.owner_id), state='preparation')
    db.add(row); db.flush()
    audit(db, actor, row, 'support_case.created', learner_id=learner_id)
    remember(db, actor, school_id, 'case.create', command, digest, row.id)
    return row


def update_case(db, actor, school_id, case_id, command):
    row = case_access(db, actor, school_id, case_id, 'support_case.write', lock=True)
    prior, digest = replay(db, actor, school_id, 'case.update', command, case_id)
    if prior: return row
    expected(row, command)
    owner = db.scalar(select(SchoolMembership).where(SchoolMembership.school_id == school_id, SchoolMembership.user_id == str(command.owner_id), *active_at(SchoolMembership,school_today(db.get(School,school_id)))))
    if owner is None or owner.role in {'guardian','technical_administrator'}: raise access_denied()
    require_learner_access(db, Actor(str(command.owner_id)), school_id, row.learner_id, 'support_case.access')
    row.concern, row.owner_id, row.state = command.concern, str(command.owner_id), command.state
    touch(row); audit(db, actor, row, 'support_case.updated')
    remember(db, actor, school_id, 'case.update', command, digest, row.id)
    return row


def create_consent(db, actor, school_id, case_id, command):
    case = case_access(db, actor, school_id, case_id, 'support_case.confirm', lock=True)
    prior, digest = replay(db, actor, school_id, 'consent.create', command, case_id)
    if prior: return db.get(EducationConsent, prior)
    binding = source_binding(db, actor, school_id, case.learner_id, command.source)
    values = command.model_dump(exclude={'request_key','source'}, mode='python')
    row = EducationConsent(school_id=school_id, learner_id=case.learner_id, case_id=case_id, **values, source=binding, confirmed_by=actor.user_id, state='confirmed')
    db.add(row); db.flush()
    depend(db, actor, school_id, case.learner_id, [binding], 'education_consent', row.id)
    audit(db, actor, row, 'education_consent.confirmed')
    remember(db, actor, school_id, 'consent.create', command, digest, row.id)
    return row


def revoke_consent(db, actor, school_id, case_id, consent_id, command):
    case, row = child(db, actor, school_id, case_id, EducationConsent, consent_id, 'support_case.confirm', lock=True)
    prior, digest = replay(db, actor, school_id, 'consent.revoke', command, consent_id)
    if prior: return row
    expected(row, command)
    if row.state != 'confirmed': raise conflict('This consent was already revoked.')
    row.state, row.revoked_reason = 'revoked', command.reason
    audit(db, actor, row, 'education_consent.revoked')
    remember(db, actor, school_id, 'consent.revoke', command, digest, row.id)
    return row


def consent(db, actor, case, consent_id, kind, at=None):
    at = at or utcnow()
    row = db.scalar(select(EducationConsent).where(EducationConsent.school_id == case.school_id, EducationConsent.learner_id == case.learner_id, EducationConsent.case_id == case.id, EducationConsent.id == str(consent_id), EducationConsent.kind == kind, EducationConsent.action_scope == 'referral_submission', EducationConsent.state == 'confirmed'))
    if row is None or row.valid_from > at or (row.valid_until is not None and row.valid_until <= at):
        raise DomainError('consent_required', 'Current sourced permission or processing basis is missing for this action.', 409)
    source_binding(db, actor, case.school_id, case.learner_id, row.source)
    return row


def referral_content(command):
    return command.model_dump(mode='json', exclude={'request_key','expected_version'})


def referral_revision(db, row):
    return db.scalar(select(ReferralRevision).where(ReferralRevision.school_id == row.school_id, ReferralRevision.referral_id == row.id, ReferralRevision.revision == row.current_revision))


def check_referral(db, actor, case, revision, at=None):
    sources(db, actor, case.school_id, case.learner_id, revision.sources)
    consent(db, actor, case, revision.processing_basis_id, 'processing_basis', at)
    if revision.permission_requirement == 'required':
        if not revision.consent_ids: raise DomainError('consent_required','Required educational consent has not been recorded.',409)
        for cid in revision.consent_ids: consent(db, actor, case, cid, 'education_action', at)
    if revision.disclosure_requirement == 'required':
        if not revision.disclosure_permission_ids: raise DomainError('disclosure_permission_required','Required disclosure permission has not been recorded.',409)
        for cid in revision.disclosure_permission_ids: consent(db, actor, case, cid, 'disclosure_permission', at)
    # Not-required determinations retain an explicit sourced human basis.
    if not revision.permission_basis.strip(): raise DomainError('permission_basis','Record the action permission determination.',409)


def save_referral(db, actor, school_id, case_id, command, referral_id=None):
    case = case_access(db, actor, school_id, case_id, 'support_case.write', lock=True)
    operation = 'referral.revise' if referral_id else 'referral.create'
    prior, digest = replay(db, actor, school_id, operation, command, referral_id or case_id)
    if prior: return db.get(Referral, prior)
    if case.state == 'closed': raise conflict('Reopen the case before preparing a referral.')
    bindings = sources(db, actor, school_id, case.learner_id, command.sources)
    if referral_id:
        _, row = child(db, actor, school_id, case_id, Referral, referral_id, 'support_case.write')
        expected(row, command)
        if row.state not in {'draft','reviewed'}: raise conflict('A submitted referral is immutable; prepare a new referral.')
        row.current_revision += 1
        row.state, row.reviewed_digest, row.reviewed_by = 'draft', None, None
        touch(row)
    else:
        row = Referral(school_id=school_id, learner_id=case.learner_id, case_id=case_id, state='draft')
        db.add(row); db.flush()
    values = command.model_dump(exclude={'request_key','expected_version','sources','consent_ids','disclosure_permission_ids','processing_basis_id'})
    revision = ReferralRevision(school_id=school_id, referral_id=row.id, revision=row.current_revision, **values, sources=bindings, consent_ids=[str(x) for x in command.consent_ids], disclosure_permission_ids=[str(x) for x in command.disclosure_permission_ids], processing_basis_id=str(command.processing_basis_id), digest=canonical_content_digest(referral_content(command)), created_by=actor.user_id)
    db.add(revision)
    # Drafting may continue while consent is missing; exact review/submission fails closed.
    depend(db, actor, school_id, case.learner_id, bindings, 'referral', row.id, row.current_revision)
    audit(db, actor, row, 'referral.drafted', case_id=case.id)
    remember(db, actor, school_id, operation, command, digest, row.id)
    return row


def review_referral(db, actor, school_id, case_id, referral_id, command):
    case, row = child(db, actor, school_id, case_id, Referral, referral_id, 'support_case.confirm', lock=True)
    prior, digest = replay(db, actor, school_id, 'referral.review', command, referral_id)
    if prior: return row
    expected(row, command)
    revision = referral_revision(db, row)
    if row.state != 'draft' or revision.digest != command.content_digest: raise conflict('Review the exact current referral draft.')
    check_referral(db, actor, case, revision)
    row.state, row.reviewed_digest, row.reviewed_by = 'reviewed', revision.digest, actor.user_id
    audit(db, actor, row, 'referral.reviewed')
    remember(db, actor, school_id, 'referral.review', command, digest, row.id)
    return row


def contact_referral(db, actor, school_id, case_id, referral_id, command):
    case, row = child(db, actor, school_id, case_id, Referral, referral_id, 'support_case.write', lock=True)
    if command.kind == 'submission':
        require_authority(db, actor, school_id, 'support_case.submit', case.learner_id, case.id)
    prior, digest = replay(db, actor, school_id, 'referral.contact', command, referral_id)
    if prior: return row
    expected(row, command)
    revision = referral_revision(db, row)
    binding = source_binding(db, actor, school_id, case.learner_id, command.source) if command.source else None
    if command.actual_contact and command.occurred_at > utcnow(): raise DomainError('contact_future','An actual contact must already have occurred.',422)
    if command.kind == 'submission':
        if row.state != 'reviewed' or row.reviewed_digest != revision.digest or command.recipient != revision.recipient:
            raise conflict('Submission must match the exact reviewed referral and recipient.')
        check_referral(db, actor, case, revision)
        check_referral(db, actor, case, revision, command.occurred_at)
        row.state, case.state = 'submitted', 'referral_submitted'
    elif command.kind == 'receipt':
        if row.state != 'submitted': raise conflict('Record a receipt only for a submitted referral.')
        row.state, case.state = 'receipt_received', 'awaiting_basis'
    else:
        if row.state not in {'submitted','receipt_received','follow_up'}: raise conflict('Follow up an actual submitted referral.')
        row.state, case.state = 'follow_up', 'follow_up'
    values = command.model_dump(exclude={'request_key','expected_version','source'})
    db.add(ReferralContact(school_id=school_id, referral_id=row.id, referral_revision=row.current_revision, **values, source=binding, recorded_by=actor.user_id))
    if binding: depend(db, actor, school_id, case.learner_id, [binding], 'referral_contact', row.id, row.current_revision)
    touch(row); audit(db, actor, row, 'referral.'+command.kind, actual_contact=command.actual_contact)
    audit(db, actor, case, 'support_case.progressed')
    remember(db, actor, school_id, 'referral.contact', command, digest, row.id)
    return row


def import_assessment(db, actor, school_id, case_id, command):
    case = case_access(db, actor, school_id, case_id, 'support_case.write', lock=True)
    prior, digest = replay(db, actor, school_id, 'assessment.import', command, case_id)
    if prior: return db.get(ExpertAssessment, prior)
    if command.assessment_at > utcnow() or (command.valid_until and command.valid_until <= command.assessment_at):
        raise DomainError('assessment_period','Check the assessment issue and validity dates.',422)
    binding = source_binding(db, actor, school_id, case.learner_id, command.source)
    row = ExpertAssessment(school_id=school_id, learner_id=case.learner_id, case_id=case.id, issuer=command.issuer, assessment_at=command.assessment_at, valid_until=command.valid_until, source=binding, state='proposed')
    db.add(row); db.flush()
    bindings = [binding]
    for value in command.recommendations:
        b = source_binding(db, actor, school_id, case.learner_id, value.source)
        bindings.append(b)
        db.add(Recommendation(school_id=school_id, assessment_id=row.id, **value.model_dump(exclude={'source'}), source=b))
    depend(db, actor, school_id, case.learner_id, bindings, 'expert_assessment', row.id)
    audit(db, actor, row, 'expert_assessment.imported')
    remember(db, actor, school_id, 'assessment.import', command, digest, row.id)
    return row


def confirm_assessment(db, actor, school_id, case_id, assessment_id, command):
    case, row = child(db, actor, school_id, case_id, ExpertAssessment, assessment_id, 'support_case.confirm', lock=True)
    prior, digest = replay(db, actor, school_id, 'assessment.confirm', command, assessment_id)
    if prior: return row
    expected(row, command)
    if row.state != 'proposed': raise conflict('Confirm only a proposed expert assessment.')
    bindings = [row.source] + [r.source for r in db.scalars(select(Recommendation).where(Recommendation.school_id == school_id, Recommendation.assessment_id == row.id))]
    sources(db, actor, school_id, case.learner_id, bindings)
    row.state, row.confirmed_by = 'confirmed', actor.user_id
    audit(db, actor, row, 'expert_assessment.confirmed')
    remember(db, actor, school_id, 'assessment.confirm', command, digest, row.id)
    return row


def decision_revision(db, row):
    return db.scalar(select(DecisionRevision).where(DecisionRevision.school_id == row.school_id, DecisionRevision.decision_id == row.id, DecisionRevision.revision == row.current_revision))


def save_decision(db, actor, school_id, case_id, command, decision_id=None):
    case = case_access(db, actor, school_id, case_id, 'support_case.write', lock=True)
    operation = 'decision.revise' if decision_id else 'decision.import'
    prior, digest = replay(db, actor, school_id, operation, command, decision_id or case_id)
    if prior: return db.get(EducationDecision, prior)
    if command.issued_at > utcnow(): raise DomainError('decision_future','Record an actually issued authority decision.',422)
    binding = source_binding(db, actor, school_id, case.learner_id, command.source)
    if decision_id:
        _, row = child(db, actor, school_id, case_id, EducationDecision, decision_id, 'support_case.write')
        expected(row, command)
        # The prior authoritative revision remains available until human confirmation
        # of the replacement, but current-plan validation flags the pending change.
        row.current_revision += 1
        touch(row)
    else:
        row = EducationDecision(school_id=school_id, learner_id=case.learner_id, case_id=case.id, state='proposed')
        db.add(row); db.flush()
    rev = DecisionRevision(school_id=school_id, decision_id=row.id, revision=row.current_revision, **command.model_dump(exclude={'request_key','expected_version','source','provisions'}), source=binding, state='proposed')
    db.add(rev); db.flush()
    bindings = [binding]
    for value in command.provisions:
        b = source_binding(db, actor, school_id, case.learner_id, value.source)
        bindings.append(b)
        db.add(DecisionProvision(school_id=school_id, decision_revision_id=rev.id, **value.model_dump(exclude={'source'}), source=b))
    depend(db, actor, school_id, case.learner_id, bindings, 'education_decision', row.id, row.current_revision)
    audit(db, actor, row, 'education_decision.imported', revision_id=rev.id)
    remember(db, actor, school_id, operation, command, digest, row.id)
    return row


def confirm_decision(db, actor, school_id, case_id, decision_id, command):
    case, row = child(db, actor, school_id, case_id, EducationDecision, decision_id, 'support_case.confirm', lock=True)
    require_authority(db, actor, school_id, 'education_decision.confirm', case.learner_id, case.id)
    prior, digest = replay(db, actor, school_id, 'decision.confirm', command, decision_id)
    if prior: return row
    expected(row, command)
    revision = decision_revision(db, row)
    if revision.state != 'proposed': raise conflict('This decision revision has already been reviewed.')
    provisions = db.scalars(select(DecisionProvision).where(DecisionProvision.school_id == school_id, DecisionProvision.decision_revision_id == revision.id)).all()
    sources(db, actor, school_id, case.learner_id, [revision.source] + [p.source for p in provisions])
    for old in db.scalars(select(DecisionRevision).where(DecisionRevision.school_id == school_id, DecisionRevision.decision_id == row.id, DecisionRevision.state == 'confirmed')):
        old.state = 'superseded'
    revision.state, revision.confirmed_by, revision.confirmation_at = 'confirmed', actor.user_id, utcnow()
    row.state, case.state = 'confirmed', 'decision_received'
    touch(row); audit(db, actor, row, 'education_decision.confirmed', revision_id=revision.id)
    audit(db, actor, case, 'support_case.decision_received')
    # Persist a visible impact task in BC05 without rewriting any plan or goal.
    from spesped.contexts.plans.service import record_decision_impacts
    record_decision_impacts(db, actor, row, revision)
    record_recommendation_differences(db,actor,case,row,revision,provisions)
    remember(db, actor, school_id, 'decision.confirm', command, digest, row.id)
    return row


def provision_reference(case, decision, revision, provision):
    return DecisionProvisionReference(SubjectScope(SchoolId.parse(case.school_id), LearnerId.parse(case.learner_id), CaseId.parse(case.id)), DecisionId.parse(decision.id), RevisionId.parse(revision.id), DecisionProvisionId.parse(provision.id))


def entitlement_quantity(case, decision, revision, provision):
    if provision.amount is None: return None
    return EntitlementQuantity(provision.amount, QuantityUnit(provision.unit), EffectivePeriod(provision.effective_from, provision.effective_until), SupportCategory(provision.category), provision.clause, CountingBasis(provision.counting_basis), provision_reference(case, decision, revision, provision))


def resolve_provision(db, actor, school_id, learner_id, decision_id, revision_id, provision_id, at=None, *, historical=False):
    decision = db.scalar(select(EducationDecision).where(EducationDecision.school_id == school_id, EducationDecision.learner_id == learner_id, EducationDecision.id == str(decision_id)))
    if decision is None: raise access_denied()
    case = case_access(db, actor, school_id, decision.case_id)
    revision = db.scalar(select(DecisionRevision).where(DecisionRevision.school_id == school_id, DecisionRevision.decision_id == decision.id, DecisionRevision.id == str(revision_id)))
    provision = db.scalar(select(DecisionProvision).where(DecisionProvision.school_id == school_id, DecisionProvision.decision_revision_id == str(revision_id), DecisionProvision.id == str(provision_id)))
    if revision is None or provision is None: raise access_denied()
    if not historical and (revision.revision != decision.current_revision or revision.state != 'confirmed'):
        raise DomainError('decision_changed','The decision basis has changed or awaits confirmation.',409)
    if historical and revision.confirmed_by is None: raise conflict('This historical provision was never confirmed.')
    sources(db, actor, school_id, learner_id, [revision.source,provision.source])
    if at is not None and not (provision.effective_from <= at < provision.effective_until):
        raise DomainError('decision_period','The provision does not apply at this time.',409)
    return case, decision, revision, provision


def entitlements_for_learner(db, actor, school_id, learner_id, at=None):
    require_learner_access(db, actor, school_id, learner_id, 'plans.read')
    at = at or utcnow()
    result = []
    for decision in db.scalars(select(EducationDecision).where(EducationDecision.school_id == school_id, EducationDecision.learner_id == learner_id, EducationDecision.state == 'confirmed')):
        case = case_access(db, actor, school_id, decision.case_id)
        revision = decision_revision(db, decision)
        if revision.state != 'confirmed': continue
        for provision in db.scalars(select(DecisionProvision).where(DecisionProvision.school_id == school_id, DecisionProvision.decision_revision_id == revision.id)):
            if not provision.effective_from <= at < provision.effective_until: continue
            sources(db, actor, school_id, learner_id, [revision.source,provision.source])
            result.append({'reference':provision_reference(case,decision,revision,provision), 'quantity':entitlement_quantity(case,decision,revision,provision), 'category':provision.category, 'subject':provision.subject, 'organization':provision.organization, 'competence':provision.competence})
    return result


def create_clarification(db,actor,school_id,case_id,command):
    from .models import CaseClarification
    case=case_access(db,actor,school_id,case_id,'support_case.write',lock=True)
    prior,digest=replay(db,actor,school_id,'clarification.create',command,case_id)
    if prior: return db.get(CaseClarification,prior)
    binding=source_binding(db,actor,school_id,case.learner_id,command.source) if command.source else None
    row=CaseClarification(school_id=school_id,learner_id=case.learner_id,case_id=case.id,kind=command.kind,description=command.description,owner_id=case.owner_id,due_at=command.due_at,source=binding,state='open')
    db.add(row);db.flush()
    if binding: depend(db,actor,school_id,case.learner_id,[binding],'case_clarification',row.id)
    audit(db,actor,row,'support_case.clarification_opened')
    remember(db,actor,school_id,'clarification.create',command,digest,row.id)
    return row


def resolve_clarification(db,actor,school_id,case_id,clarification_id,command):
    from .models import CaseClarification
    case,row=child(db,actor,school_id,case_id,CaseClarification,clarification_id,'support_case.confirm',lock=True)
    prior,digest=replay(db,actor,school_id,'clarification.resolve',command,clarification_id)
    if prior:return row
    expected(row,command)
    if row.state != 'open':raise conflict('This clarification has already been resolved.')
    row.state,row.resolution,row.resolved_by,row.resolved_at='resolved',command.resolution,actor.user_id,utcnow()
    audit(db,actor,row,'support_case.clarification_resolved')
    remember(db,actor,school_id,'clarification.resolve',command,digest,row.id)
    return row


def record_recommendation_differences(db,actor,case,decision,revision,provisions):
    """Separate expert recommendations from rights; create an owned human task."""
    from .models import CaseClarification
    assessments=db.scalars(select(ExpertAssessment).where(ExpertAssessment.school_id == case.school_id,ExpertAssessment.case_id == case.id,ExpertAssessment.state == 'confirmed')).all()
    for assessment in assessments:
        for rec in db.scalars(select(Recommendation).where(Recommendation.school_id == case.school_id,Recommendation.assessment_id == assessment.id)):
            candidates=[p for p in provisions if p.category == rec.category and p.subject == rec.subject]
            differs=not candidates
            for provision in candidates:
                comparable=(rec.effective_from,rec.effective_until,rec.counting_basis) == (provision.effective_from,provision.effective_until,provision.counting_basis)
                if rec.amount is not None and provision.amount is not None:
                    differs |= not comparable or rec.amount*(60 if rec.unit == 'hours' else 1) != provision.amount*(60 if provision.unit == 'hours' else 1)
                else:
                    differs |= rec.amount != provision.amount
            if differs:
                row=CaseClarification(school_id=case.school_id,learner_id=case.learner_id,case_id=case.id,kind='recommendation_difference',description='The confirmed expert recommendation and decision provision differ or have different quantity bases. Review each source; the decision remains separately authoritative.',owner_id=case.owner_id,source=rec.source,reference_id=revision.id,state='open')
                db.add(row);db.flush();audit(db,actor,row,'support_case.recommendation_difference',recommendation_id=rec.id,decision_revision_id=revision.id)


def decision_bindings(db,actor,school_id,learner_id,decision_id,revision_id,provision_ids):
    """Scoped exact source bindings for dependent contexts' authorized views.

    Returning identifiers grants no source-prose access. Consumers still apply
    the actor-aware evidence check, even for a superseded historical decision.
    """
    decision=db.scalar(select(EducationDecision).where(EducationDecision.school_id == school_id,EducationDecision.learner_id == learner_id,EducationDecision.id == decision_id))
    if decision is None:raise access_denied()
    case_access(db,actor,school_id,decision.case_id)
    revision=db.scalar(select(DecisionRevision).where(DecisionRevision.school_id == school_id,DecisionRevision.decision_id == decision.id,DecisionRevision.id == revision_id))
    if revision is None:raise access_denied()
    bindings=[revision.source]
    for provision_id in provision_ids:
        provision=db.scalar(select(DecisionProvision).where(DecisionProvision.school_id == school_id,DecisionProvision.decision_revision_id == revision.id,DecisionProvision.id == provision_id))
        if provision is None:raise access_denied()
        bindings.append(provision.source)
    return bindings
