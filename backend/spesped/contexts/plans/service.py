"""BC05 application service. Never changes previously recorded pedagogical content."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from spesped.audit import record_audit
from spesped.auth import require_authority, require_learner_access, require_school_access
from spesped.db import utcnow
from spesped.domain import ApprovalBinding, EffectivePeriod, EntitlementQuantity, QuantityUnit, CountingBasis, RevisionId, SubjectScope, SchoolId, LearnerId, UserId, canonical_content_digest
from spesped.errors import DomainError, access_denied
from spesped.contexts.identity.models import Learner
from spesped.contexts.evidence.projections import confirmed_binding_is_current
from spesped.contexts.entitlements import service as entitlements
from spesped.contexts.entitlements.common import (audit, conflict, depend, expected, replay, remember, source_binding, sources, source_status, authorized_projection, touch)
from .models import (LearnerSupportProfile, ProfileStatement, ProfileReview, IndividualEducationPlan, PlanRevision, LearningGoal, GoalRevision, Adaptation, PlanContribution, ProvisionAllocation, PlanApproval, PlanImpact, PlanCommand, PlanEvent)


def event(db, actor, row, action, **payload):
    audit(db, actor, row, action, PlanEvent, **payload)


def check_access(db, actor, school_id, learner_id, action='plans.read'):
    membership = require_school_access(db, actor, school_id)
    if membership.role in {'guardian','technical_administrator'}: raise access_denied()
    return require_learner_access(db, actor, school_id, learner_id, action)


def profile(db, actor, school_id, learner_id, action='profile.read', create=False):
    check_access(db, actor, school_id, learner_id, action)
    row = db.scalar(select(LearnerSupportProfile).where(LearnerSupportProfile.school_id == school_id, LearnerSupportProfile.learner_id == learner_id).with_for_update())
    if row is None and create:
        row = LearnerSupportProfile(school_id=school_id, learner_id=learner_id, state='active')
        db.add(row); db.flush()
    return row


def propose_profile(db, actor, school_id, learner_id, command):
    parent = profile(db, actor, school_id, learner_id, 'profile.write', create=True)
    prior, digest = replay(db, actor, school_id, 'profile.propose', command, learner_id, PlanCommand)
    if prior: return db.get(ProfileStatement, prior)
    binding = source_binding(db, actor, school_id, learner_id, command.source)
    if command.observed_at > utcnow(): raise DomainError('observation_future','The statement must be based on an existing observation.',422)
    if command.replaces_id:
        original = db.scalar(select(ProfileStatement).where(ProfileStatement.school_id == school_id, ProfileStatement.profile_id == parent.id, ProfileStatement.id == str(command.replaces_id)))
        if original is None: raise access_denied()
        if original.state not in {'confirmed','disputed'} or original.category != command.category:
            raise conflict('Replace a current statement in the same category.')
    row = ProfileStatement(school_id=school_id, profile_id=parent.id, category=command.category, content=command.content, source=binding, observed_at=command.observed_at, proposed_by=actor.user_id, replaces_id=str(command.replaces_id) if command.replaces_id else None, state='proposed')
    db.add(row); db.flush()
    depend(db, actor, school_id, learner_id, [binding], 'support_profile', row.id)
    touch(parent); event(db, actor, row, 'profile.statement_proposed')
    remember(db, actor, school_id, 'profile.propose', command, digest, row.id, PlanCommand)
    return row


def review_profile(db, actor, school_id, learner_id, statement_id, command):
    parent = profile(db, actor, school_id, learner_id, 'profile.confirm')
    if parent is None: raise access_denied()
    require_authority(db, actor, school_id, 'profile.confirm', learner_id)
    row = db.scalar(select(ProfileStatement).where(ProfileStatement.school_id == school_id, ProfileStatement.profile_id == parent.id, ProfileStatement.id == statement_id).with_for_update())
    if row is None: raise access_denied()
    prior, digest = replay(db, actor, school_id, 'profile.review', command, statement_id, PlanCommand)
    if prior: return row
    expected(row, command)
    if row.state not in {'proposed','confirmed','disputed'}: raise conflict('This statement is no longer current.')
    if command.outcome == 'confirmed':
        source_binding(db, actor, school_id, learner_id, row.source)
        if row.replaces_id:
            old = db.get(ProfileStatement, row.replaces_id)
            if old.state not in {'confirmed','disputed'}: raise conflict('The statement to replace changed.')
            old.state = 'replaced'
            db.add(ProfileReview(school_id=school_id, statement_id=old.id, outcome='replaced', reason=command.reason, reviewer_id=actor.user_id))
    row.state, row.review_reason, row.reviewed_at = command.outcome, command.reason, utcnow()
    row.confirmed_by = actor.user_id if command.outcome == 'confirmed' else row.confirmed_by
    db.add(ProfileReview(school_id=school_id, statement_id=row.id, outcome=command.outcome, reason=command.reason, reviewer_id=actor.user_id))
    touch(parent); event(db, actor, row, 'profile.statement_reviewed')
    remember(db, actor, school_id, 'profile.review', command, digest, row.id, PlanCommand)
    return row


def profile_view(db, actor, school_id, learner_id, history=False, brief=False, offset=0, limit=50):
    parent = profile(db, actor, school_id, learner_id, 'profile.brief' if brief else 'profile.read')
    if parent is None: return {'items':[], 'total':0, 'clarifications':[]}
    query = select(ProfileStatement).where(ProfileStatement.school_id == school_id, ProfileStatement.profile_id == parent.id)
    if not history: query = query.where(ProfileStatement.state.in_(['proposed','confirmed','disputed']))
    if brief: query = query.where(ProfileStatement.state == 'confirmed', ProfileStatement.category.in_(['strength','interest','language','communication','support_strategy']))
    items, clarifications = [], []
    for row in db.scalars(query.order_by(ProfileStatement.created_at, ProfileStatement.id)):
        if brief:
            # The brief is a curated projection. It contains no original excerpt or
            # document path and does not require dossier/evidence-read authority.
            current=confirmed_binding_is_current(db,school_id,learner_id,str(row.source['evidence_id']),row.source['evidence_revision'],str(row.source['link_id']))
            status = 'current' if current else 'review_required'
        else:
            status = source_status(db, actor, school_id, learner_id, [row.source])
        if status != 'current' or row.state == 'disputed':
            clarifications.append({'statement_id':row.id,'reason':'source_changed' if status != 'current' else 'disputed'})
        if brief and status != 'current': continue
        view = {'id':row.id,'version':row.version,'category':row.category,'content':row.content if status == 'current' else None,'state':row.state,'source_status':status,'observed_at':row.observed_at,'confirmed_by':row.confirmed_by,'reviewed_at':row.reviewed_at}
        if not brief:
            view.update(source=row.source if status == 'current' else None,replaces_id=row.replaces_id)
            reviewed=profile_review_projection(db,actor,school_id,learner_id,row,{'review_reason':row.review_reason},('review_reason',))
            view['review_reason']=reviewed['review_reason']
        items.append(view)
    record_audit(db, actor, school_id, 'profile.brief_read' if brief else 'profile.read', 'support_profile', parent.id)
    return {'id':parent.id,'version':parent.version,'items':items[offset:offset+limit],'total':len(items),'clarifications':clarifications[offset:offset+limit]}


def plan(db, actor, school_id, plan_id, action='plans.read', lock=False):
    query = select(IndividualEducationPlan).where(IndividualEducationPlan.school_id == school_id, IndividualEducationPlan.id == plan_id)
    if lock: query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None: raise access_denied()
    check_access(db, actor, school_id, row.learner_id, action)
    return row


def current_revision(db, row):
    return db.scalar(select(PlanRevision).where(PlanRevision.school_id == row.school_id, PlanRevision.plan_id == row.id, PlanRevision.revision == row.current_revision))


def children(db, model, revision):
    return db.scalars(select(model).where(model.school_id == revision.school_id, model.plan_revision_id == revision.id).order_by(model.id)).all()


def json_value(value):
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, Decimal): return format(value.normalize(), 'f')
    return value


def content_row(row, names):
    return {name:json_value(getattr(row,name)) for name in names}


GOAL_FIELDS = ('id','goal_id','parent_goal_id','status','title','expected_action','arena','support','responsibility','evaluation_method','curriculum_reference','effective_from','effective_until')
REVISION_FIELDS = ('id','plan_id','revision','title','rationale','organization','responsibility','evaluation_method','participation_record','decision_id','decision_revision_id','effective_from','effective_until','origin','sources','original_approval')


def snapshot(db, revision):
    value = content_row(revision, REVISION_FIELDS)
    value['goals'] = [content_row(g, GOAL_FIELDS) for g in children(db, GoalRevision, revision)]
    value['adaptations'] = [content_row(a, ('id','goal_id','measure','arena','responsibility','evaluation_method')) for a in children(db,Adaptation,revision)]
    value['contributions'] = [content_row(c, ('id','goal_id','participant','role','content','disagreement','response','occurred_at','source')) for c in children(db,PlanContribution,revision)]
    value['allocations'] = [content_row(a, ('id','provision_id','decision_id','decision_revision_id','amount','unit','counting_basis','effective_from','effective_until')) for a in children(db,ProvisionAllocation,revision)]
    return value


def all_bindings(db, revision):
    bindings = list(revision.sources)
    if revision.original_approval: bindings.append(revision.original_approval['source'])
    bindings.extend(c.source for c in children(db,PlanContribution,revision))
    return bindings


def validate_plan_basis(db, actor, row, revision, *, bounds=True, historical=False):
    sources(db, actor, row.school_id, row.learner_id, projection_bindings(db,actor,row,revision))
    allocations = children(db, ProvisionAllocation, revision)
    if row.kind == 'ordinary_teaching':
        if revision.decision_id or allocations: raise DomainError('ordinary_scope','Ordinary teaching plans must not claim decision entitlements.',422)
    else:
        if not revision.decision_id or not allocations:
            raise DomainError('decision_required','An individual education plan requires confirmed exact decision provisions.',409)
        for allocation in allocations:
            if (allocation.decision_id, allocation.decision_revision_id) != (revision.decision_id,revision.decision_revision_id): raise DomainError('decision_scope','All allocations must use the plan decision revision.',422)
            case, decision, decision_rev, provision = entitlements.resolve_provision(db, actor, row.school_id, row.learner_id, allocation.decision_id, allocation.decision_revision_id, allocation.provision_id, historical=historical)
            if bounds:
                if revision.effective_from < decision_rev.effective_from or revision.effective_until > decision_rev.effective_until or allocation.effective_from < provision.effective_from or allocation.effective_until > provision.effective_until:
                    raise DomainError('decision_period','The plan or allocation exceeds the decision period. Prepare a revision task.',409)
                # No proportional invention: quantities are compared over the exact
                # reference period. A different period needs an explicit authority basis.
                granted = entitlements.entitlement_quantity(case,decision,decision_rev,provision)
                if granted:
                    if allocation.amount is None or allocation.counting_basis != provision.counting_basis or (allocation.effective_from,allocation.effective_until) != (provision.effective_from,provision.effective_until):
                        raise DomainError('quantity_basis','Use the provision counting basis and exact reference period.',409)
                    quantity = EntitlementQuantity(allocation.amount, QuantityUnit(allocation.unit), EffectivePeriod(allocation.effective_from, allocation.effective_until), granted.category, granted.decision_clause, CountingBasis(allocation.counting_basis), granted.decision_provision)
                    if quantity.total_minutes() > granted.total_minutes(): raise DomainError('decision_exceeded','The plan proposal exceeds a confirmed decision provision.',409)
                elif allocation.amount is not None: raise DomainError('quantity_basis','This physical adaptation provision has no quantitative entitlement.',409)
        if bounds and not any(entitlements.resolve_provision(db,actor,row.school_id,row.learner_id,a.decision_id,a.decision_revision_id,a.provision_id,historical=historical)[3].category == 'individually_adapted_education' for a in allocations):
            raise DomainError('ito_required','An IEP requires an individually adapted education provision.',409)
    if revision.original_approval:
        from datetime import datetime
        if datetime.fromisoformat(revision.original_approval['approved_at']) > utcnow(): raise DomainError('approval_future','Original approval must already have occurred.',422)
    if canonical_content_digest(snapshot(db,revision)) != revision.content_digest:
        raise conflict('The stored content no longer matches its review digest.')


def save_plan(db, actor, school_id, learner_id, command, plan_id=None):
    check_access(db, actor, school_id, learner_id, 'plans.write')
    # Serialize independent creations/revisions for this pupil, including activation.
    db.scalar(select(Learner).where(Learner.school_id == school_id,Learner.id == learner_id).with_for_update())
    operation = 'plan.revise' if plan_id else 'plan.create'
    prior, digest = replay(db, actor, school_id, operation, command, plan_id or learner_id, PlanCommand)
    if prior: return db.get(IndividualEducationPlan,prior)
    if plan_id:
        row = plan(db,actor,school_id,plan_id,'plans.write',lock=True)
        if row.learner_id != learner_id: raise access_denied()
        expected(row,command)
        row.current_revision += 1; touch(row)
    else:
        row = IndividualEducationPlan(school_id=school_id,learner_id=learner_id,kind=command.kind,state='draft')
        db.add(row); db.flush()
    binding_values = sources(db,actor,school_id,learner_id,command.sources)
    if command.original_approval: source_binding(db,actor,school_id,learner_id,command.original_approval.source)
    values = command.model_dump(exclude={'request_key','expected_version','kind','sources','original_approval','goals','adaptations','contributions','allocations','decision_id','decision_revision_id'})
    revision = PlanRevision(school_id=school_id,plan_id=row.id,revision=row.current_revision,**values,decision_id=str(command.decision_id) if command.decision_id else None,decision_revision_id=str(command.decision_revision_id) if command.decision_revision_id else None,sources=binding_values,original_approval=command.original_approval.model_dump(mode='json') if command.original_approval else None,created_by=actor.user_id,content_digest='pending',state='draft')
    db.add(revision); db.flush()
    goal_ids=set()
    for value in command.goals:
        if value.goal_id:
            goal = db.scalar(select(LearningGoal).where(LearningGoal.school_id == school_id,LearningGoal.plan_id == row.id,LearningGoal.id == str(value.goal_id)))
            if goal is None:
                if db.get(LearningGoal,str(value.goal_id)) is not None: raise access_denied()
                goal=LearningGoal(id=str(value.goal_id),school_id=school_id,plan_id=row.id)
                db.add(goal);db.flush()
        else:
            goal = LearningGoal(school_id=school_id,plan_id=row.id)
            db.add(goal);db.flush()
        goal_ids.add(goal.id)
        db.add(GoalRevision(school_id=school_id,goal_id=goal.id,plan_revision_id=revision.id,**value.model_dump(exclude={'goal_id','parent_goal_id'}),parent_goal_id=str(value.parent_goal_id) if value.parent_goal_id else None))
    db.flush()
    for goal in children(db,GoalRevision,revision):
        if goal.parent_goal_id:
            if goal.parent_goal_id not in goal_ids or goal.parent_goal_id == goal.goal_id: raise DomainError('goal_parent','A subgoal must refer to another goal within this plan revision.',422)
            seen={goal.goal_id}; parent_id=goal.parent_goal_id
            by_id={g.goal_id:g for g in children(db,GoalRevision,revision)}
            while parent_id:
                if parent_id in seen: raise DomainError('goal_cycle','Goal hierarchy must not contain a cycle.',422)
                seen.add(parent_id);parent_id=by_id[parent_id].parent_goal_id
    # An omitted historic identity is explicitly closed in the comparison view;
    # its prior goal version stays immutable and accessible to historic sessions.
    for value in command.adaptations:
        if value.goal_id and str(value.goal_id) not in goal_ids: raise DomainError('goal_scope','Adaptation refers to a goal outside this revision.',422)
        db.add(Adaptation(school_id=school_id,plan_revision_id=revision.id,**value.model_dump(exclude={'goal_id'}),goal_id=str(value.goal_id) if value.goal_id else None))
    for value in command.contributions:
        if value.goal_id and str(value.goal_id) not in goal_ids: raise DomainError('goal_scope','Contribution refers to a goal outside this revision.',422)
        if value.occurred_at > utcnow(): raise DomainError('contribution_future','Record an actual contribution or explain missing participation.',422)
        binding=source_binding(db,actor,school_id,learner_id,value.source)
        db.add(PlanContribution(school_id=school_id,plan_revision_id=revision.id,**value.model_dump(exclude={'goal_id','source'}),goal_id=str(value.goal_id) if value.goal_id else None,source=binding))
    for value in command.allocations:
        entitlements.resolve_provision(db,actor,school_id,learner_id,str(value.decision_id),str(value.decision_revision_id),str(value.provision_id))
        db.add(ProvisionAllocation(school_id=school_id,plan_revision_id=revision.id,**value.model_dump(exclude={'decision_id','decision_revision_id','provision_id'}),decision_id=str(value.decision_id),decision_revision_id=str(value.decision_revision_id),provision_id=str(value.provision_id)))
    db.flush()
    revision.content_digest=canonical_content_digest(snapshot(db,revision))
    validate_plan_basis(db,actor,row,revision,bounds=False)
    depend(db,actor,school_id,learner_id,all_bindings(db,revision),'education_plan',row.id,row.current_revision)
    event(db,actor,row,'plan.revision_created',revision_id=revision.id)
    remember(db,actor,school_id,operation,command,digest,row.id,PlanCommand)
    return row


def lifecycle(db, actor, school_id, plan_id, command, transition):
    # Every overlapping plan command takes pupil then plan locks. The first
    # scoped read identifies the pupil without taking the plan lock. Refresh
    # after waiting so an earlier ORM identity cannot hide a committed revision.
    row=plan(db,actor,school_id,plan_id,'plans.write')
    db.scalar(select(Learner).where(Learner.id == row.learner_id,Learner.school_id == school_id).with_for_update())
    row=plan(db,actor,school_id,plan_id,'plans.write',lock=True)
    grant=None
    if transition in {'approve','activate'}:
        grant=require_authority(db,actor,school_id,'plans.approve',row.learner_id)
    operation='plan.'+transition
    prior,digest=replay(db,actor,school_id,operation,command,plan_id,PlanCommand)
    if prior: return row
    expected(row,command)
    revision=current_revision(db,row)
    if revision.id != str(command.revision_id) or revision.content_digest != command.content_digest: raise conflict('Review the exact current plan content.')
    required={'review':'draft','approve':'in_review','activate':'approved'}[transition]
    if revision.state != required: raise conflict('The plan is not in the required review state.')
    validate_plan_basis(db,actor,row,revision)
    if transition == 'review':
        revision.state,revision.reviewed_by='in_review',actor.user_id
    elif transition == 'approve':
        now=utcnow()
        scope=SubjectScope(SchoolId.parse(school_id),LearnerId.parse(row.learner_id))
        binding=ApprovalBinding.create(scope=scope,revision_id=RevisionId.parse(revision.id),content=snapshot(db,revision),attachments=(),reviewer_id=UserId.parse(actor.user_id),authority=grant.id,approved_at=now)
        revision.state,revision.approved_by,revision.approved_at='approved',actor.user_id,now
        revision.approval_binding={'revision_id':revision.id,'revision_digest':binding.revision_digest,'school_id':school_id,'learner_id':row.learner_id,'reviewer_id':actor.user_id,'authority_grant_id':grant.id,'approved_at':now.isoformat()}
    else:
        if revision.effective_until <= utcnow(): raise DomainError('plan_expired','An expired plan cannot be newly activated.',409)
        binding=revision.approval_binding
        if not binding or binding['revision_digest'] != canonical_content_digest(snapshot(db,revision)): raise conflict('The approval is stale.')
        # Any school/learner plan of the same kind must use one dated current basis.
        for other in db.scalars(select(IndividualEducationPlan).where(IndividualEducationPlan.school_id == school_id,IndividualEducationPlan.learner_id == row.learner_id,IndividualEducationPlan.kind == row.kind,IndividualEducationPlan.active_revision_id.is_not(None)).with_for_update()):
            old=db.get(PlanRevision,other.active_revision_id)
            if old and old.id != revision.id:
                if revision.effective_from < max(old.effective_from,old.activated_at): raise DomainError('activation_period','A replacement cannot retroactively change the previously activated goal period.',409)
                old.state='historical';old.activation_until=revision.effective_from
                other.active_revision_id=None;touch(other)
        revision.state,revision.activated_at='active',utcnow()
        row.active_revision_id=revision.id
        for impact in db.scalars(select(PlanImpact).where(PlanImpact.school_id == school_id,PlanImpact.plan_id == row.id,PlanImpact.state == 'open')):
            if impact.kind == 'decision_changed' and impact.new_reference == revision.decision_revision_id:
                impact.state='resolved';impact.resolved_by_revision_id=revision.id
    row.state='active' if row.active_revision_id else revision.state
    touch(row)
    db.add(PlanApproval(school_id=school_id,plan_revision_id=revision.id,kind=transition,digest=revision.content_digest,reason=command.reason,authority_grant_id=grant.id if grant else None,reviewer_id=actor.user_id))
    event(db,actor,row,operation,revision_id=revision.id)
    remember(db,actor,school_id,operation,command,digest,row.id,PlanCommand)
    return row


def record_decision_impacts(db,actor,decision,new_revision):
    for revision in db.scalars(select(PlanRevision).where(PlanRevision.school_id == decision.school_id,PlanRevision.decision_id == decision.id,PlanRevision.decision_revision_id != new_revision.id,PlanRevision.state.in_(['draft','in_review','approved','active']))):
        row=db.get(IndividualEducationPlan,revision.plan_id)
        prior=db.scalar(select(PlanImpact).where(PlanImpact.school_id == decision.school_id,PlanImpact.plan_revision_id == revision.id,PlanImpact.kind == 'decision_changed',PlanImpact.new_reference == new_revision.id))
        if prior is None:
            impact=PlanImpact(school_id=decision.school_id,learner_id=row.learner_id,plan_id=row.id,plan_revision_id=revision.id,kind='decision_changed',old_reference=revision.decision_revision_id,new_reference=new_revision.id,state='open')
            db.add(impact);db.flush();event(db,actor,impact,'plan.decision_review_required')


def goal_reference(db,actor,school_id,learner_id,goal_revision_id,at=None,historical=False):
    check_access(db,actor,school_id,learner_id,'plans.read')
    goal=db.scalar(select(GoalRevision).where(GoalRevision.school_id == school_id,GoalRevision.id == str(goal_revision_id)))
    if goal is None: raise access_denied()
    revision=db.get(PlanRevision,goal.plan_revision_id)
    row=plan(db,actor,school_id,revision.plan_id)
    if row.learner_id != learner_id: raise access_denied()
    if revision.activated_at is None or goal.status != 'active': raise DomainError('goal_not_active','Use an authorized activated goal revision.',409)
    if not historical and at is None: at=utcnow()
    if not historical and revision.state not in {'active','historical'}: raise DomainError('goal_historical','The goal belongs to an inactive plan revision.',409)
    validate_plan_basis(db,actor,row,revision,historical=historical)
    if at is not None:
        end=min(goal.effective_until,revision.activation_until) if revision.activation_until else goal.effective_until
        if not goal.effective_from <= at < end: raise DomainError('goal_period','The goal version does not apply at that time.',409)
    return {'id':goal.id,'goal_id':goal.goal_id,'plan_id':row.id,'plan_revision_id':revision.id,'kind':row.kind,**content_row(goal,GOAL_FIELDS),'plan_digest':revision.content_digest,'decision_id':revision.decision_id,'decision_revision_id':revision.decision_revision_id}


def validate_goal_reference(db,actor,school_id,learner_id,goal_revision_id):
    """Evidence may refer to an activated historical version, preserving its dates."""
    return goal_reference(db,actor,school_id,learner_id,goal_revision_id,historical=True)


def active_goals(db,actor,school_id,learner_id,at=None):
    check_access(db,actor,school_id,learner_id,'plans.read')
    at=at or utcnow();result=[]
    for revision in db.scalars(select(PlanRevision).join(IndividualEducationPlan,IndividualEducationPlan.id == PlanRevision.plan_id).where(PlanRevision.school_id == school_id,IndividualEducationPlan.learner_id == learner_id,PlanRevision.activated_at.is_not(None),PlanRevision.effective_from <= at,PlanRevision.effective_until > at)):
        if revision.activation_until is not None and at >= revision.activation_until: continue
        for goal in children(db,GoalRevision,revision):
            if goal.status == 'active' and goal.effective_from <= at < goal.effective_until:
                result.append(goal_reference(db,actor,school_id,learner_id,goal.id,at))
    return result


def compare(db,row,old_revision,new_revision):
    before={g.goal_id:g for g in children(db,GoalRevision,old_revision)} if old_revision else {}
    after={g.goal_id:g for g in children(db,GoalRevision,new_revision)}
    result=[]
    fields=tuple(f for f in GOAL_FIELDS if f not in {'id','goal_id'})
    for goal_id in sorted(before.keys()|after.keys()):
        old,new=before.get(goal_id),after.get(goal_id)
        state='closed' if new is None or new.status == 'closed' else 'added' if old is None else 'continued' if content_row(old,fields)==content_row(new,fields) else 'changed'
        result.append({'goal_id':goal_id,'change':state,'old_revision_id':old.id if old else None,'new_revision_id':new.id if new else None})
    return result


def profile_review_projection(db,actor,school_id,learner_id,statement,value,prose_fields):
    # A replacement review can discuss both statements. Its reason must remain
    # protected when either linked interpretation becomes stale or inaccessible.
    related=[statement]
    if statement.replaces_id:
        previous=db.scalar(select(ProfileStatement).where(ProfileStatement.school_id == school_id,ProfileStatement.profile_id == statement.profile_id,ProfileStatement.id == statement.replaces_id))
        if previous: related.append(previous)
    related.extend(db.scalars(select(ProfileStatement).where(ProfileStatement.school_id == school_id,ProfileStatement.profile_id == statement.profile_id,ProfileStatement.replaces_id == statement.id)))
    return authorized_projection(db,actor,school_id,learner_id,value,[row.source for row in related],prose_fields)


def projection_bindings(db,actor,row,revision):
    bindings=all_bindings(db,revision)
    if revision.decision_id:
        allocations=children(db,ProvisionAllocation,revision)
        bindings.extend(entitlements.decision_bindings(db,actor,row.school_id,row.learner_id,revision.decision_id,revision.decision_revision_id,[a.provision_id for a in allocations]))
    return bindings
