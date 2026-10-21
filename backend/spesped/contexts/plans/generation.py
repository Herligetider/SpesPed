"""Unconfirmed IEP proposals with exact, transitive, currently authorized lineage.

The gateway owns model execution. This consumer never supplies an approval,
participation claim, curriculum association, legal provision or effective date.
"""
import json
from uuid import uuid4
from sqlalchemy import select
from pydantic import ValidationError
from spesped.db import utcnow
from spesped.domain import canonical_content_digest
from spesped.errors import DomainError,access_denied
from spesped.contexts.entitlements import service as entitlements
from spesped.contexts.entitlements.common import expected,replay,remember,sources,depend,conflict
from spesped.contexts.entitlements.models import ExpertAssessment,Recommendation
from spesped.contexts.platform import service as gateway
from spesped.contexts.platform.contracts import SourceInput,SourceRef,GenerationRequest,release_schema
from . import service
from .models import PlanGenerationBasis,PlanProposalReview,PlanCommand,PlanRevision,ProfileStatement,ProvisionAllocation
from .schemas import RevisePlan

FIELDS=('title','rationale','organization','responsibility','evaluation_method')
GOAL_FIELDS=('title','expected_action','arena','support','responsibility','evaluation_method')


def load_basis(db,actor,school_id,identity,action='plans.write'):
    basis=db.scalar(select(PlanGenerationBasis).where(PlanGenerationBasis.school_id == school_id,PlanGenerationBasis.id == str(identity)))
    if basis is None:raise access_denied()
    row=service.plan(db,actor,school_id,basis.plan_id,action)
    if row.learner_id != basis.learner_id:raise access_denied()
    return row,basis


def collect(db,actor,row,revision,assessment_ids,profile_ids):
    """Resolve exact owner records and source permissions, never metadata as prose access."""
    service.validate_plan_basis(db,actor,row,revision)
    if row.kind != 'individual_education':raise DomainError('iep_basis_required','IEP proposals require a human-authored IEP with confirmed decision provisions.',409)
    allocations=service.children(db,ProvisionAllocation,revision)
    case,_,_,_=entitlements.resolve_provision(db,actor,row.school_id,row.learner_id,revision.decision_id,revision.decision_revision_id,allocations[0].provision_id)
    bindings=service.projection_bindings(db,actor,row,revision)
    assessments=[]
    for identity in assessment_ids:
        _,assessment=entitlements.child(db,actor,row.school_id,case.id,ExpertAssessment,str(identity),'support_case.read')
        if assessment.learner_id != row.learner_id or assessment.state != 'confirmed' or not assessment.confirmed_by or (assessment.valid_until and assessment.valid_until <= utcnow()):
            raise DomainError('assessment_basis_changed','Select a current confirmed expert assessment for this pupil and case.',409)
        recommendations=list(db.scalars(select(Recommendation).where(Recommendation.school_id == row.school_id,Recommendation.assessment_id == assessment.id).order_by(Recommendation.id)))
        bindings.extend([assessment.source]+[r.source for r in recommendations])
        assessments.append({**service.content_row(assessment,('id','version','case_id','issuer','assessment_at','valid_until','source','confirmed_by')),'recommendations':[service.content_row(r,('id','category','subject','content','amount','unit','counting_basis','effective_from','effective_until','source')) for r in recommendations]})
    parent=service.profile(db,actor,row.school_id,row.learner_id) if profile_ids else None
    profile=[]
    for identity in profile_ids:
        statement=db.scalar(select(ProfileStatement).where(ProfileStatement.school_id == row.school_id,ProfileStatement.profile_id == (parent.id if parent else None),ProfileStatement.id == str(identity)))
        if statement is None:raise access_denied()
        if statement.state != 'confirmed' or not statement.confirmed_by:raise DomainError('profile_basis_changed','Select confirmed current profile statements.',409)
        bindings.append(statement.source)
        profile.append(service.content_row(statement,('id','version','category','content','source','confirmed_by','observed_at')))
    sources(db,actor,row.school_id,row.learner_id,bindings)
    return {'plan':service.snapshot(db,revision),'assessments':assessments,'profile':profile,'source_bindings':bindings,'curriculum_context':'unavailable','adaptation_generation':'unavailable','participation':'human_record_only','proposal_limits':'Pedagogical text only. Dates, rights, quantities, participation and approval remain human-owned.'}


def require_basis(db,actor,row,basis,*,current=False):
    revision=db.scalar(select(PlanRevision).where(PlanRevision.school_id == row.school_id,PlanRevision.plan_id == row.id,PlanRevision.id == basis.plan_revision_id))
    if revision is None or basis.learner_id != row.learner_id:raise access_denied()
    if current and service.current_revision(db,row).id != revision.id:raise conflict('The plan changed after this basis was selected. Prepare a new basis and regenerate.')
    if canonical_content_digest(basis.content) != basis.digest:raise conflict('The immutable generation basis digest changed.')
    content=collect(db,actor,row,revision,[a['id'] for a in basis.content['assessments']],[p['id'] for p in basis.content['profile']])
    if canonical_content_digest(content) != basis.digest:raise DomainError('generation_basis_changed','The selected exact assessment, profile, decision or goal basis changed.',409)
    return revision


def create_basis(db,actor,school_id,plan_id,command):
    row=service.plan(db,actor,school_id,plan_id,'plans.write',lock=True)
    prior,digest=replay(db,actor,school_id,'plan.generation_basis',command,plan_id,PlanCommand)
    if prior:
        _,basis=load_basis(db,actor,school_id,prior)
        require_basis(db,actor,row,basis)
        return basis
    expected(row,command)
    revision=service.current_revision(db,row)
    if revision.id != str(command.plan_revision_id):raise conflict('Select the exact current plan revision.')
    content=collect(db,actor,row,revision,[str(i) for i in command.assessment_ids],[str(i) for i in command.profile_statement_ids])
    dependencies={'goals':[{'id':g['id'],'goal_id':g['goal_id']} for g in content['plan']['goals']],'revision_digest':revision.content_digest,'source_bindings':content['source_bindings'],'assessments':[{**{k:a[k] for k in ('id','version','case_id','confirmed_by')},'recommendation_ids':[r['id'] for r in a['recommendations']]} for a in content['assessments']],'profile':[{k:p[k] for k in ('id','version','confirmed_by','source')} for p in content['profile']],'allocations':[{k:a[k] for k in ('decision_id','decision_revision_id','provision_id')} for a in content['plan']['allocations']],'lineage':revision.generation_lineage or {}}
    basis=PlanGenerationBasis(school_id=school_id,learner_id=row.learner_id,plan_id=row.id,plan_revision_id=revision.id,content=content,digest=canonical_content_digest(content),dependencies=dependencies,dependency_digest=canonical_content_digest(dependencies),created_by=actor.user_id)
    db.add(basis);db.flush()
    depend(db,actor,school_id,row.learner_id,content['source_bindings'],'education_plan',row.id,row.current_revision)
    service.event(db,actor,row,'plan.generation_basis_selected',basis_id=basis.id)
    remember(db,actor,school_id,'plan.generation_basis',command,digest,basis.id,PlanCommand)
    return basis


def basis_view(db,actor,school_id,identity):
    row,basis=load_basis(db,actor,school_id,identity,'plans.read')
    require_basis(db,actor,row,basis)
    return {'id':basis.id,'plan_id':row.id,'plan_revision_id':basis.plan_revision_id,'digest':basis.digest,'content':basis.content,'unconfirmed':True,'curriculum_context':'unavailable','adaptation_generation':'unavailable'}


def suggestion_history(db,actor,school_id,identity,runtime,*,offset=0,limit=50):
    row=service.plan(db,actor,school_id,identity,'plans.write')
    revision=service.current_revision(db,row)
    basis_ids=list(db.scalars(select(PlanGenerationBasis.id).where(
        PlanGenerationBasis.school_id == school_id,PlanGenerationBasis.learner_id == row.learner_id,
        PlanGenerationBasis.plan_id == row.id,PlanGenerationBasis.plan_revision_id == revision.id)))
    result=gateway.source_job_summaries(db,actor,school_id,row.learner_id,
        'iep_drafting',basis_ids,runtime,offset=offset,limit=limit)
    outcomes=dict(db.execute(select(PlanProposalReview.job_id,PlanProposalReview.outcome).where(
        PlanProposalReview.school_id == school_id,PlanProposalReview.plan_id == row.id,
        PlanProposalReview.job_id.in_([item['id'] for item in result['items']]))).all())
    for item in result['items']:item['review_outcome']=outcomes.get(item['id'])
    return result | {'scope':'current_plan_revision','plan_revision_id':revision.id}


def resolve_generation_source(db,actor,school_id,learner_id,purpose,reference):
    if purpose != 'iep_drafting' or reference.kind != 'plan_basis' or reference.revision != 1:raise access_denied()
    row,basis=load_basis(db,actor,school_id,str(reference.source_id))
    if row.learner_id != learner_id:raise access_denied()
    # Historical selected output must stay readable after a later draft is made;
    # current target revision is additionally enforced at request/diff/apply.
    require_basis(db,actor,row,basis)
    return SourceInput(reference,school_id,learner_id,purpose,json.dumps(basis.content,sort_keys=True,separators=(',',':'),ensure_ascii=False),media_type='text/plain',provenance='school_data')


def request_suggestion(db,actor,school_id,plan_id,command,runtime):
    row,basis=load_basis(db,actor,school_id,str(command.basis_id))
    if row.id != plan_id:raise access_denied()
    require_basis(db,actor,row,basis,current=True)
    return gateway.create_job(db,actor,school_id,GenerationRequest(learner_id=row.learner_id,purpose='iep_drafting',policy_id=command.policy_id,release_id=command.release_id,logical_request_key=command.request_key,sources=[SourceRef(kind='plan_basis',source_id=basis.id,revision=1)]),runtime)


def proposal_digest(job):
    return canonical_content_digest({'job_id':job.id,'source_manifest':job.source_manifest,'release_digest':job.release_digest,'policy_version':job.policy_version,'output':job.output})


def suggestion(db,actor,school_id,plan_id,basis_id,job_id,runtime,*,current=True):
    row,basis=load_basis(db,actor,school_id,basis_id)
    if row.id != plan_id:raise access_denied()
    job=gateway.current_job(db,actor,school_id,job_id,runtime,lock=True)
    if job.purpose != 'iep_drafting' or job.learner_id != row.learner_id or [s['reference'] for s in job.source_manifest] != [{'kind':'plan_basis','source_id':basis.id,'revision':1}]:raise access_denied()
    if job.state != 'succeeded' or job.output is None:raise DomainError('suggestion_unavailable','No usable suggestion is available. Continue in the manual plan editor.',409)
    revision=require_basis(db,actor,row,basis,current=current)
    try:output=release_schema('iep-draft.v1').model_validate({k:v for k,v in job.output.items() if k not in {'unconfirmed','requires_human_review','schema_version'}}).model_dump(mode='json')
    except ValueError:raise DomainError('invalid_suggestion','The result is not a typed IEP proposal.',409) from None
    ids={g['goal_id'] for g in basis.content['plan']['goals']}
    if any(g['target_goal_id'] is not None and g['target_goal_id'] not in ids for g in output['goals']):raise DomainError('proposal_goal_scope','A suggested goal does not belong to the exact selected plan revision.',409)
    return row,revision,basis,job,output


def diff(db,actor,school_id,plan_id,basis_id,job_id,runtime):
    row,revision,basis,job,output=suggestion(db,actor,school_id,plan_id,basis_id,job_id,runtime)
    if db.scalar(select(PlanProposalReview.id).where(PlanProposalReview.school_id == school_id,PlanProposalReview.job_id == job.id)):
        raise conflict('This proposal has already been reviewed. Generate a new proposal to reconsider it.')
    before={g['goal_id']:g for g in basis.content['plan']['goals']}
    return {'plan_id':row.id,'expected_version':row.version,'plan_revision_id':revision.id,'basis_id':basis.id,'job_id':job.id,'proposal_digest':proposal_digest(job),'unconfirmed':True,'requires_human_review':True,'fields':[{'field':f,'before':getattr(revision,f),'proposed':output[f]} for f in FIELDS if output[f] is not None],'goals':[{'proposal':g,'before':before.get(g['target_goal_id'])} for g in output['goals']],'missing_evidence':output['missing_evidence'],'source_manifest':job.source_manifest,'curriculum_context':'unavailable','adaptation_generation':'unavailable'}


def command_content(db,revision):
    data=service.snapshot(db,revision)
    for field in ('id','plan_id','revision','generation_lineage'):data.pop(field,None)
    for kind in ('goals','adaptations','contributions','allocations'):
        for child in data[kind]:child.pop('id',None)
    return data


def review(db,actor,school_id,plan_id,command,runtime):
    # Lock pupil first, matching manual save/lifecycle order. Never commit inside
    # this consumer: selection, revision, receipt and outbox are one transaction.
    row=service.plan(db,actor,school_id,plan_id,'plans.write')
    from spesped.contexts.identity.models import Learner
    db.scalar(select(Learner).where(Learner.school_id == school_id,Learner.id == row.learner_id).with_for_update())
    row=service.plan(db,actor,school_id,plan_id,'plans.write',lock=True)
    prior,digest=replay(db,actor,school_id,'plan.suggestion_review',command,plan_id,PlanCommand)
    row,original,basis,job,output=suggestion(db,actor,school_id,plan_id,str(command.basis_id),str(command.job_id),runtime,current=not bool(prior))
    if command.proposal_digest != proposal_digest(job) or str(command.plan_revision_id) != original.id:raise conflict('The exact proposal or selected plan revision changed.')
    if prior:return row
    expected(row,command)
    if db.scalar(select(PlanProposalReview.id).where(PlanProposalReview.school_id == school_id,PlanProposalReview.job_id == job.id)):raise conflict('This proposal has already been reviewed.')
    revision=original
    if command.outcome == 'applied':
        data=command_content(db,original);lineage={};goals={g['goal_id']:g for g in data['goals']}
        # Selected new text is a locally authored draft. An original import's
        # approval remains an immutable fact about that earlier document only.
        if data['origin'] == 'imported':
            data['origin']='authored';data['original_approval']=None
        entry={'job_id':job.id,'basis_id':basis.id,'proposal_digest':proposal_digest(job)}
        for field in command.selected_fields:
            if output[field] is None:raise DomainError('selection_unavailable','A selected field has no proposal.',422)
            data[field]=output[field];lineage[field]=entry
        selected={g['proposal_key']:g for g in output['goals']}
        new={g.proposal_key:g for g in command.new_goals}
        needed={k for k in command.selected_goal_keys if k in selected and selected[k]['target_goal_id'] is None}
        if set(new) != needed:raise DomainError('goal_human_basis','Every selected new goal requires human dates and curriculum reference; extra choices are invalid.',422)
        for key in command.selected_goal_keys:
            if key not in selected:raise DomainError('selection_unavailable','Select a goal in this exact proposal.',422)
            proposed=selected[key];identity=proposed['target_goal_id']
            if identity is None:
                identity=str(uuid4());choice=new[key]
                if choice.parent_goal_id is not None and str(choice.parent_goal_id) not in goals:raise DomainError('goal_parent','A human-selected parent must belong to this exact current plan revision.',422)
                goal={'goal_id':identity,'parent_goal_id':str(choice.parent_goal_id) if choice.parent_goal_id else None,'status':'active','curriculum_reference':choice.curriculum_reference,'effective_from':choice.effective_from,'effective_until':choice.effective_until}
                data['goals'].append(goal)
            else:goal=goals[identity]
            for field in GOAL_FIELDS:
                goal[field]=proposed[field];lineage[f'goals.{identity}.{field}']=entry
        try:revised=RevisePlan.model_validate({**data,'request_key':'proposal:'+canonical_content_digest({'actor':actor.user_id,'key':command.request_key}),'expected_version':row.version})
        except ValidationError:raise DomainError('proposal_plan_invalid','Selected goals must fit the human-owned plan period and plan structure.',422) from None
        row=service.save_plan(db,actor,school_id,row.learner_id,revised,row.id,generation_lineage=lineage)
        revision=service.current_revision(db,row)
    db.add(PlanProposalReview(school_id=school_id,plan_id=row.id,plan_revision_id=revision.id,basis_id=basis.id,job_id=job.id,proposal_digest=proposal_digest(job),outcome=command.outcome,selected_fields=command.selected_fields,selected_goal_keys=command.selected_goal_keys,reviewer_id=actor.user_id,reason=command.reason))
    service.event(db,actor,row,'plan.suggestion_reviewed',job_id=job.id,outcome=command.outcome)
    remember(db,actor,school_id,'plan.suggestion_review',command,digest,row.id,PlanCommand)
    return row


def validate_lineage(db,actor,row,revision):
    """Full actor-aware dependency reauthorization, including historical output."""
    checked=set()
    for entry in (revision.generation_lineage or {}).values():
        token=(entry['basis_id'],entry['job_id'])
        if token in checked:continue
        checked.add(token)
        owner,basis=load_basis(db,actor,row.school_id,entry['basis_id'],'plans.read')
        if owner.id != row.id:raise access_denied()
        require_basis(db,actor,owner,basis)
        if not gateway.job_binding_is_current(db,row.school_id,entry['job_id'],db.info.get('ai_gateway_runtime') or db.info.get('plans_runtime') or db.info.get('teaching_runtime')):
            raise DomainError('generation_processing_changed','The processing policy or reviewed model basis changed.',409)


def lineage_status(db,actor,row,revision):
    try:validate_lineage(db,actor,row,revision);return 'current'
    except DomainError:return 'review_required'


def review_history(db,actor,school_id,plan_id,offset=0,limit=50):
    row=service.plan(db,actor,school_id,plan_id)
    records=list(db.scalars(select(PlanProposalReview).where(PlanProposalReview.school_id == school_id,PlanProposalReview.plan_id == plan_id).order_by(PlanProposalReview.reviewed_at.desc(),PlanProposalReview.id)))
    items=[]
    for record in records[offset:offset+limit]:
        status='current'
        try:
            _,basis=load_basis(db,actor,school_id,record.basis_id,'plans.read')
            require_basis(db,actor,row,basis)
            if not gateway.job_binding_is_current(db,school_id,record.job_id,db.info.get('ai_gateway_runtime') or db.info.get('plans_runtime') or db.info.get('teaching_runtime')):status='review_required'
        except DomainError:status='review_required'
        value=service.content_row(record,('id','plan_revision_id','basis_id','job_id','proposal_digest','outcome','selected_fields','selected_goal_keys','reviewer_id','reviewed_at'))
        value.update(reason=record.reason if status == 'current' else None,source_status=status)
        items.append(value)
    return {'items':items,'total':len(records)}
