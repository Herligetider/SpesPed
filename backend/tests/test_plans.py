from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
from uuid import uuid4
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import func,inspect,select
from sqlalchemy.orm.exc import StaleDataError
from spesped.auth import Actor
from spesped.db import utcnow
from spesped.domain import EntitlementQuantity
from spesped.contexts.identity.models import AuditRecord,AuthorityGrant,Learner,StaffAssignment
from spesped.contexts.evidence.models import Derivative
from spesped.contexts.entitlements.models import ReferralContact,EntitlementEvent,SupportCase
from spesped.contexts.entitlements.service import entitlements_for_learner
from spesped.contexts.plans.models import IndividualEducationPlan,PlanRevision,GoalRevision,PlanEvent
from spesped.contexts.plans.service import validate_goal_reference
from plans_fixtures import env,login,base,retry,expected,evidence,support_case,period,decision_payload,confirmed_decision,plan_payload,activate,key


def post(client,path,headers,payload,status=201):
    response=client.post(path,headers=headers,json=payload)
    assert response.status_code == status,response.text
    return response.json()


def test_profile_confirmation_dispute_correction_history_and_assistant_projection(env):
    client,factory,app,ids=env;headers=login(client)
    binding,item=evidence(client,ids,headers)
    path=base(ids)+f'/learners/{ids["a"]}/support-profile'
    first=post(client,path+'/statements',headers,retry(category='support_strategy',content='Synthetic visual word cards help',source=binding,observed_at=(utcnow()-timedelta(days=2)).isoformat()))
    assert client.get(path).json()['items'][0]['state'] == 'proposed'
    first=post(client,path+f'/statements/{first["id"]}/review',headers,expected(first,outcome='confirmed',reason='Checked with learner and teacher'),200)
    second=post(client,path+'/statements',headers,retry(category='support_strategy',content='Synthetic learner prefers objects now',source=binding,observed_at=(utcnow()-timedelta(days=1)).isoformat(),replaces_id=first['id']))
    assert client.get(path).json()['total'] == 2  # Proposals do not overwrite confirmation.
    second=post(client,path+f'/statements/{second["id"]}/review',headers,expected(second,outcome='disputed',reason='Two staff accounts differ'),200)
    assert client.get(path).json()['clarifications'][0]['reason'] == 'disputed'
    second=post(client,path+f'/statements/{second["id"]}/review',headers,expected(second,outcome='confirmed',reason='Learner confirmed current preference'),200)
    history=client.get(path+'?history=true').json()['items']
    assert [x['state'] for x in history] == ['replaced','confirmed']
    login(client,'assistant')
    brief=client.get(path+'/brief');assert brief.status_code == 200,brief.text
    assert brief.json()['items'][0]['content'] == 'Synthetic learner prefers objects now'
    assert 'source' not in brief.json()['items'][0]
    assert client.get(path).status_code == 403
    assert client.get(base(ids)+f'/evidence/{item["id"]}').status_code == 403


def test_case_creation_no_implicit_rights_scope_denial_and_teacher_cannot_sign(env):
    client,factory,app,ids=env;headers=login(client)
    payload=retry(concern='Synthetic protected concern',owner_id=ids['reviewer'])
    row=post(client,base(ids)+f'/learners/{ids["a"]}/support-cases',headers,payload)
    assert client.get(base(ids)+f'/support-cases/{row["id"]}').status_code == 403
    assert client.post(base(ids)+f'/learners/{ids["a"]}/support-cases',headers=headers,json=payload).json()['id'] == row['id']
    assert client.post(base(ids)+f'/learners/{ids["a"]}/support-cases',headers=headers,json={**payload,'concern':'Different'}).status_code == 409
    for name in ('teacher','tech','guardian'):
        login(client,name)
        assert client.get(base(ids)+f'/support-cases/{row["id"]}').status_code == 403
    headers=login(client)
    plan=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,plan_payload())
    plan=post(client,base(ids)+f'/education-plans/{plan["id"]}/review',headers,expected(plan,revision_id=plan['content']['id'],content_digest=plan['content_digest'],reason='Ready for review'),200)
    teacher_headers=login(client,'teacher')
    assert client.post(base(ids)+f'/education-plans/{plan["id"]}/approve',headers=teacher_headers,json=expected(plan,revision_id=plan['content']['id'],content_digest=plan['content_digest'],reason='Attempt approval without authority')).status_code == 403


def test_referral_full_authored_review_submission_receipt_planned_followup_and_retry(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers)
    path=base(ids)+f'/support-cases/{case["id"]}'
    consents=[]
    for kind in ('education_action','processing_basis'):
        consents.append(post(client,path+'/consents',headers,retry(kind=kind,purpose='Synthetic educational referral',action_scope='referral_submission',representative='Synthetic guardian' if kind == 'education_action' else 'Synthetic school controller',representative_capacity='Sourced authority for this action',valid_from=(utcnow()-timedelta(days=50)).isoformat(),source=binding)))
    payload=retry(concern='Synthetic reading concern',prior_measures='Visual reading support tried',observed_outcomes='Persistent difficulty observed',requested_assessment='Assess educational support need',learner_view='Wants shorter text',guardian_view='Supports assessment',recipient='Synthetic expert service',sources=[binding],consent_ids=[consents[0]['id']],disclosure_requirement='not_required_with_basis',disclosure_permission_ids=[],disclosure_basis='Synthetic sourced statutory referral disclosure authorization',permission_requirement='required',permission_basis='Sourced educational permission',processing_basis_id=consents[1]['id'])
    referral=post(client,path+'/referrals',headers,payload)
    assert referral['state'] == 'draft'
    review_payload=expected(referral,content_digest=referral['content']['digest'],reason='Checked sources, participation, recipient and permission')
    referral=post(client,path+f'/referrals/{referral["id"]}/review',headers,review_payload,200)
    submission=expected(referral,kind='submission',actual_contact=True,occurred_at=(utcnow()-timedelta(minutes=10)).isoformat(),recipient='Synthetic expert service',channel='secure_external_system',external_reference='synthetic-submission-001',note='Manually recorded actual external submission',source=binding)
    referral=post(client,path+f'/referrals/{referral["id"]}/contacts',headers,submission,200)
    retry_response=post(client,path+f'/referrals/{referral["id"]}/contacts',headers,submission,200)
    assert len(retry_response['contacts']) == 1
    receipt=expected(referral,kind='receipt',actual_contact=True,occurred_at=(utcnow()-timedelta(minutes=5)).isoformat(),recipient='Synthetic expert service',channel='secure_external_system',external_reference='synthetic-receipt-001',note='Receipt verified from original',source=binding)
    referral=post(client,path+f'/referrals/{referral["id"]}/contacts',headers,receipt,200)
    planned=expected(referral,kind='follow_up',actual_contact=False,occurred_at=(utcnow()+timedelta(days=14)).isoformat(),recipient='Synthetic expert service',channel='planned',note='Call if assessment not received')
    referral=post(client,path+f'/referrals/{referral["id"]}/contacts',headers,planned,200)
    assert referral['state'] == 'follow_up' and referral['contacts'][-1]['actual_contact'] is False
    assert client.get(path).json()['state'] == 'follow_up'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReferralContact)) == 3
        assert db.scalar(select(EntitlementEvent).where(EntitlementEvent.event_type == 'referral.submission'))
    # Submission history cannot be edited as another draft revision.
    revised={**payload,'expected_version':referral['version'],'request_key':key()}
    assert client.post(path+f'/referrals/{referral["id"]}/revisions',headers=headers,json=revised).status_code == 409


def test_referral_processing_ground_does_not_substitute_for_educational_consent(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers)
    path=base(ids)+f'/support-cases/{case["id"]}'
    ground=post(client,path+'/consents',headers,retry(kind='processing_basis',purpose='Synthetic statutory school task',action_scope='referral_submission',representative='Synthetic controller',representative_capacity='Sourced processing basis',valid_from=(utcnow()-timedelta(days=5)).isoformat(),source=binding))
    payload=retry(concern='Concern',prior_measures='Support tried',observed_outcomes='Observed needs',requested_assessment='Educational assessment',learner_view='Recorded',guardian_view='Recorded',recipient='Synthetic expert service',sources=[binding],consent_ids=[ground['id']],disclosure_requirement='not_required_with_basis',disclosure_permission_ids=[],disclosure_basis='Synthetic sourced statutory referral disclosure authorization',permission_requirement='required',permission_basis='Requires separate education permission',processing_basis_id=ground['id'])
    row=post(client,path+'/referrals',headers,payload)
    result=client.post(path+f'/referrals/{row["id"]}/review',headers=headers,json=expected(row,content_digest=row['content']['digest'],reason='Try incorrect consent category'))
    assert result.status_code == 409 and result.json()['error']['code'] == 'consent_required'
    assert client.get(path+f'/referrals/{row["id"]}').json()['state'] == 'draft'


def test_decision_import_confirmation_typed_separate_provisions_and_expert_comparison(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers)
    path=base(ids)+f'/support-cases/{case["id"]}';dates=period()
    expert=post(client,path+'/expert-assessments',headers,retry(issuer='Synthetic expert service',assessment_at=(utcnow()-timedelta(days=70)).isoformat(),source=binding,recommendations=[{'category':'individually_adapted_education','subject':'reading','content':'Recommended reading support','amount':'150','unit':'hours','counting_basis':'learner_time','source':binding,**dates}]))
    expert=post(client,path+f'/expert-assessments/{expert["id"]}/confirm',headers,expected(expert,reason='Verified expert original'),200)
    payload=decision_payload(binding)
    p=payload['provisions'][0]
    payload['provisions'] += [{**p,'clause':'2','category':'personal_assistance','amount':'50','counting_basis':'staff_time'},{**p,'clause':'3','category':'physical_adaptation','amount':None,'unit':None,'counting_basis':None,'content':'Adjustable desk'}]
    decision=post(client,path+'/decisions',headers,payload)
    assert decision['content']['state'] == 'proposed'
    with factory() as db: assert entitlements_for_learner(db,Actor(ids['reviewer']),ids['school'],ids['a']) == []
    decision=post(client,path+f'/decisions/{decision["id"]}/confirm',headers,expected(decision,reason='Verified binding provisions and authority'),200)
    comparison=client.get(path+'/comparison').json()
    assert comparison['expert_recommendations'][0]['recommendations'][0]['amount'] == '150.0000'
    assert len(comparison['binding_decisions'][0]['provisions']) == 3
    with factory() as db:
        quantities=entitlements_for_learner(db,Actor(ids['reviewer']),ids['school'],ids['a'])
        assert len(quantities) == 3
        assert isinstance(quantities[0]['quantity'],EntitlementQuantity)
        assert quantities[0]['reference'].decision_revision.value
        with pytest.raises(ValueError): quantities[0]['quantity'].add(quantities[1]['quantity'])


def test_full_authored_iep_goals_contributions_exact_approval_revisions_and_historical_binding(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers);decision=confirmed_decision(client,ids,headers,case,binding)
    payload=plan_payload(binding,decision)
    row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,payload)
    assert row['clarifications'] == [],row
    row=activate(client,ids,headers,row)
    old_revision=row['content']['id'];old_goal=row['content']['goals'][0]
    assert row['content']['contributions'][0]['disagreement'] is True
    active=client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals').json()
    assert active['items'][0]['id'] == old_goal['id']
    next_payload={**payload,'request_key':key(),'expected_version':row['version']};next_payload.pop('kind')
    next_payload['effective_from']=utcnow().isoformat()
    next_payload['goals']=[{**payload['goals'][0],'goal_id':old_goal['goal_id'],'effective_from':next_payload['effective_from'],'expected_action':'Read two short sentences with visual support'}]
    revised=post(client,base(ids)+f'/education-plans/{row["id"]}/revisions',headers,next_payload)
    assert revised['active_revision_id'] == old_revision
    old=client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals/{old_goal["id"]}').json()
    assert old['expected_action'] == 'Read a short sentence independently'
    comparison=client.get(base(ids)+f'/education-plans/{row["id"]}/compare',params={'old_revision_id':old_revision,'new_revision_id':revised['content']['id']}).json()
    assert comparison['items'][0]['change'] == 'changed'
    revised=activate(client,ids,headers,revised)
    assert revised['content']['goals'][0]['goal_id'] == old_goal['goal_id']
    assert revised['content']['goals'][0]['id'] != old_goal['id']
    historical=client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals/{old_goal["id"]}?historical=true')
    assert historical.status_code == 200 and historical.json()['expected_action'] == old_goal['expected_action']
    with factory() as db:
        assert validate_goal_reference(db,Actor(ids['reviewer']),ids['school'],ids['a'],old_goal['id'])['id'] == old_goal['id']
        assert db.scalar(select(func.count()).select_from(PlanRevision)) == 2
        assert db.scalar(select(func.count()).select_from(GoalRevision)) == 2


def test_ordinary_teaching_no_fabricated_ito_and_imported_approval_provenance(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers)
    payload=plan_payload(binding,origin='imported',original_approval={'approver':'Synthetic original teacher','authority':'Documented school pedagogical responsibility','approved_at':(utcnow()-timedelta(days=3)).isoformat(),'source':binding})
    row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,payload)
    row=activate(client,ids,headers,row)
    assert row['kind'] == 'ordinary_teaching' and row['content']['decision_id'] is None and row['content']['allocations'] == []
    assert row['content']['original_approval']['approver'] == 'Synthetic original teacher'
    assert row['approval_binding']['reviewer_id'] == ids['reviewer']
    assert client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals').json()['total'] == 1
    invalid={**payload,'request_key':key(),'original_approval':None}
    assert client.post(base(ids)+f'/learners/{ids["a"]}/education-plans',headers=headers,json=invalid).status_code == 422


def test_proposal_outside_decision_quantity_counting_basis_or_period_cannot_activate(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers);decision=confirmed_decision(client,ids,headers,case,binding)
    for changes,code in [({'amount':'101'},'decision_exceeded'),({'counting_basis':'staff_time'},'quantity_basis'),({'effective_until':(utcnow()+timedelta(days=181)).isoformat()},'decision_period')]:
        payload=plan_payload(binding,decision);payload['allocations'][0].update(changes)
        row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,payload)
        assert row['clarifications'][0]['code'] == code
        result=client.post(base(ids)+f'/education-plans/{row["id"]}/review',headers=headers,json=expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Proposal needs new decision'))
        assert result.status_code == 409 and result.json()['error']['code'] == code
        assert client.get(base(ids)+f'/education-plans/{row["id"]}').json()['revision_state'] == 'draft'


def test_cross_learner_source_goal_and_case_references_are_rejected(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers,'b');case=support_case(client,factory,ids,headers)
    result=client.post(base(ids)+f'/support-cases/{case["id"]}/decisions',headers=headers,json=decision_payload(binding))
    assert result.status_code == 409
    assert client.post(base(ids)+f'/learners/{ids["a"]}/education-plans',headers=headers,json=plan_payload(binding)).status_code == 409
    row=post(client,base(ids)+f'/learners/{ids["b"]}/education-plans',headers,plan_payload(binding));row=activate(client,ids,headers,row)
    assert client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals/{row["content"]["goals"][0]["id"]}?historical=true').status_code == 403
    login(client,'teacher')
    assert client.get(base(ids)+f'/education-plans/{row["id"]}').status_code == 403
    assert client.get(f'/api/v1/schools/{ids["other_school"]}/education-plans/{row["id"]}').status_code == 403


def test_source_correction_blocks_stale_approval_redacts_profile_and_keeps_impacts(env):
    client,factory,app,ids=env;headers=login(client);binding,item=evidence(client,ids,headers)
    profile_path=base(ids)+f'/learners/{ids["a"]}/support-profile'
    statement=post(client,profile_path+'/statements',headers,retry(category='strength',content='Synthetic fluent reading',source=binding,observed_at=(utcnow()-timedelta(days=2)).isoformat()))
    post(client,profile_path+f'/statements/{statement["id"]}/review',headers,expected(statement,outcome='confirmed',reason='Checked synthetic record'),200)
    row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,plan_payload(binding))
    row=post(client,base(ids)+f'/education-plans/{row["id"]}/review',headers,expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Exact source reviewed'),200)
    corrected=client.post(base(ids)+f'/evidence/{item["id"]}/corrections',headers=headers,json={'expected_version':item['version'],'learner_id':ids['a'],'claim_type':'report','reporter':'Synthetic authority','source_type':'imported_document','certainty':'disputed','occurred_at':(utcnow()-timedelta(days=20)).isoformat(),'topic':'education','content':'Synthetic source now disputed','reason':'Synthetic contradiction discovered'})
    assert corrected.status_code == 200,corrected.text
    approval=client.post(base(ids)+f'/education-plans/{row["id"]}/approve',headers=headers,json=expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Attempt stale approval'))
    assert approval.status_code == 409 and approval.json()['error']['code'] == 'source_changed'
    assert client.get(profile_path).json()['items'][0]['content'] is None
    assert client.get(base(ids)+f'/education-plans/{row["id"]}').json()['content'].get('goals') is None
    impacts=client.get(base(ids)+f'/evidence/{item["id"]}/correction-impacts').json()
    assert impacts['total'] >= 2
    login(client,'assistant')
    assert client.get(profile_path+'/brief').json()['items'] == []


def test_new_decision_records_review_task_preserves_goal_text_and_blocks_old_plan(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers);decision=confirmed_decision(client,ids,headers,case,binding)
    row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,plan_payload(binding,decision));row=activate(client,ids,headers,row)
    payload=decision_payload(binding);payload['expected_version']=decision['version'];payload['provisions'][0]['amount']='80'
    path=base(ids)+f'/support-cases/{case["id"]}/decisions/{decision["id"]}'
    revised=post(client,path+'/revisions',headers,payload)
    revised=post(client,path+'/confirm',headers,expected(revised,reason='Confirm replaced authority decision'),200)
    impacts=client.get(base(ids)+f'/learners/{ids["a"]}/plan-change-impacts').json()
    assert impacts['total'] == 1 and impacts['items'][0]['state'] == 'open'
    assert impacts['items'][0]['new_reference'] == revised['content']['id']
    assert client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals').status_code == 409
    history=client.get(base(ids)+f'/education-plans/{row["id"]}/revisions').json()
    assert history['items'][0]['content']['goals'][0]['expected_action'] == 'Read a short sentence independently'


def test_atomic_audit_outbox_idempotency_optimistic_versions_and_migration_roundtrip(env):
    client,factory,app,ids=env;headers=login(client)
    payload=plan_payload();row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,payload)
    assert post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,payload)['id'] == row['id']
    assert client.post(base(ids)+f'/learners/{ids["a"]}/education-plans',headers=headers,json={**payload,'title':'Changed title'}).status_code == 409
    stale=expected(row,revision_id=row['content']['id'],content_digest='0'*64,reason='Wrong reviewed digest')
    assert client.post(base(ids)+f'/education-plans/{row["id"]}/review',headers=headers,json=stale).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(IndividualEducationPlan)) == 1
        assert db.scalar(select(AuditRecord).where(AuditRecord.action == 'plan.revision_created')) is not None
        assert db.scalar(select(PlanEvent).where(PlanEvent.event_type == 'plan.revision_created')) is not None
    with factory() as left,factory() as right:
        first=left.get(IndividualEducationPlan,row['id']);second=right.get(IndividualEducationPlan,row['id'])
        first.state='in_review';left.commit();second.state='approved'
        with pytest.raises(StaleDataError): right.commit()
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=app.state.settings.database_url
    command.downgrade(config,'b1_integrate_contexts')
    assert 'plans_learning_goals' not in inspect(factory.kw['bind']).get_table_names()
    with factory() as db: assert db.get(Learner,ids['a']) is not None
    command.upgrade(config,'j05_plans')
    assert 'plans_learning_goals' in inspect(factory.kw['bind']).get_table_names()


def test_dated_authority_revocation_disclosure_permission_and_owned_clarification_recovery(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers)
    path=base(ids)+f'/support-cases/{case["id"]}'
    issue=post(client,path+'/clarifications',headers,retry(kind='unclear_unit',description='Original says lessons without their length',source=binding,due_at=(utcnow()+timedelta(days=3)).isoformat()))
    assert issue['state'] == 'open' and issue['owner_id'] == ids['reviewer']
    assert client.get(path+'/clarifications').json()['total'] == 1
    assert client.get(path+'/timeline').json()['items'][-1]['kind'] == 'clarification'
    issue=post(client,path+f'/clarifications/{issue["id"]}/resolve',headers,expected(issue,resolution='Issuing authority supplied exact lesson minutes; revised source is recorded'),200)
    assert issue['state'] == 'resolved'
    # Actual case access depends on the current explicit dated grant.
    with factory.begin() as db:
        grant=db.scalar(select(AuthorityGrant).where(AuthorityGrant.case_id == case['id'],AuthorityGrant.action == 'support_case.read'))
        grant.valid_until=date.today()-timedelta(days=1);grant.valid_from=date.today()-timedelta(days=10)
    assert client.get(path+'/timeline').status_code == 403
    assert client.get(path+'/clarifications').status_code == 403


def test_sourced_disclosure_permission_is_independent_and_revocation_blocks_referral_review(env):
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers)
    path=base(ids)+f'/support-cases/{case["id"]}';consents={}
    for kind in ('education_action','processing_basis','disclosure_permission'):
        consents[kind]=post(client,path+'/consents',headers,retry(kind=kind,purpose='Synthetic referral purpose',action_scope='referral_submission',representative='Synthetic responsible representative',representative_capacity='Sourced scope and capacity for this category',valid_from=(utcnow()-timedelta(days=30)).isoformat(),source=binding))
    payload=retry(concern='Concern',prior_measures='Measures',observed_outcomes='Observed outcomes',requested_assessment='Educational assessment',learner_view='Recorded learner input',guardian_view='Recorded guardian input',recipient='Synthetic expert service',sources=[binding],consent_ids=[consents['education_action']['id']],permission_requirement='required',permission_basis='Education permission checked',processing_basis_id=consents['processing_basis']['id'],disclosure_requirement='required',disclosure_permission_ids=[consents['disclosure_permission']['id']],disclosure_basis='Sourced disclosure scope checked')
    referral=post(client,path+'/referrals',headers,payload)
    permission=consents['disclosure_permission']
    post(client,path+f'/consents/{permission["id"]}/revoke',headers,expected(permission,reason='Representative withdrew this disclosure permission'),200)
    result=client.post(path+f'/referrals/{referral["id"]}/review',headers=headers,json=expected(referral,content_digest=referral['content']['digest'],reason='Try after disclosure revocation'))
    assert result.status_code == 409 and result.json()['error']['code'] == 'consent_required'
    assert client.get(path+f'/referrals/{referral["id"]}').json()['state'] == 'draft'


def test_future_replacement_preserves_current_dated_goal_and_immutable_goal_content(env):
    from spesped.errors import DomainError
    client,factory,app,ids=env;headers=login(client)
    payload=plan_payload();row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,payload);row=activate(client,ids,headers,row)
    old_goal=row['content']['goals'][0];future=utcnow()+timedelta(days=7)
    revised={**payload,'request_key':key(),'expected_version':row['version'],'effective_from':future.isoformat()};revised.pop('kind')
    revised['goals']=[{**payload['goals'][0],'goal_id':old_goal['goal_id'],'effective_from':future.isoformat(),'title':'Synthetic next period goal'}]
    row=post(client,base(ids)+f'/education-plans/{row["id"]}/revisions',headers,revised);row=activate(client,ids,headers,row)
    assert client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals').json()['items'][0]['id'] == old_goal['id']
    future_goals=client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals',params={'at':(future+timedelta(days=1)).isoformat()}).json()
    assert future_goals['items'][0]['title'] == 'Synthetic next period goal'
    with factory() as db:
        goal=db.get(GoalRevision,old_goal['id']);goal.expected_action='Attempt to change history'
        with pytest.raises(DomainError,match='new revision'): db.commit()
        db.rollback()
        assert db.get(GoalRevision,old_goal['id']).expected_action == old_goal['expected_action']


def test_authored_goal_hierarchy_stable_ids_and_cross_plan_identity_denial(env):
    client,factory,app,ids=env;headers=login(client)
    payload=plan_payload();parent_id,child_id=key(),key()
    parent={**payload['goals'][0],'goal_id':parent_id}
    child={**payload['goals'][0],'goal_id':child_id,'parent_goal_id':parent_id,'title':'Synthetic observable subgoal'}
    payload['goals']=[parent,child]
    row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,payload)
    row=activate(client,ids,headers,row)
    assert {g['goal_id'] for g in row['content']['goals']} == {parent_id,child_id}
    assert next(g for g in row['content']['goals'] if g['goal_id'] == child_id)['parent_goal_id'] == parent_id
    stolen={**payload,'request_key':key()}
    assert client.post(base(ids)+f'/learners/{ids["a"]}/education-plans',headers=headers,json=stolen).status_code == 403
    cycle=plan_payload();left,right=key(),key();cycle['goals']=[{**parent,'goal_id':left,'parent_goal_id':right},{**child,'goal_id':right,'parent_goal_id':left}]
    assert client.post(base(ids)+f'/learners/{ids["a"]}/education-plans',headers=headers,json=cycle).status_code == 422


def test_postgres_concurrent_plan_retry_has_one_aggregate_audit_and_event(env):
    if env[1].kw['bind'].dialect.name != 'postgresql': pytest.skip('Real PostgreSQL contention scenario')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from spesped.contexts.plans.schemas import CreatePlan
    from spesped.contexts.plans.service import save_plan
    client,factory,app,ids=env
    command_data=CreatePlan(**plan_payload());barrier=Barrier(2)
    def competing():
        with factory() as db:
            barrier.wait()
            row=save_plan(db,Actor(ids['reviewer']),ids['school'],ids['a'],command_data)
            db.commit();return row.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:competing(),range(2)))
    assert results[0] == results[1]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(IndividualEducationPlan)) == 1
        assert db.scalar(select(func.count()).select_from(PlanEvent).where(PlanEvent.event_type == 'plan.revision_created')) == 1
        assert db.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action == 'plan.revision_created')) == 1


# Independent review regressions retained in the normal candidate suite.
def revoke_authority(factory,ids,action):
    with factory.begin() as db:
        grant=db.scalar(select(AuthorityGrant).where(AuthorityGrant.school_id==ids['school'],AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action==action))
        grant.state='revoked'

def test_review_regression_approval_replay_rechecks_revoked_signing_authority(env):
    c,f,app,ids=env;h=login(c)
    row=post(c,base(ids)+f'/learners/{ids["a"]}/education-plans',h,plan_payload())
    path=base(ids)+f'/education-plans/{row["id"]}'
    row=post(c,path+'/review',h,expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Reviewed'),200)
    cmd=expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Approved')
    post(c,path+'/approve',h,cmd,200);revoke_authority(f,ids,'plans.approve')
    response=c.post(path+'/approve',headers=h,json=cmd)
    assert response.status_code==403,response.text
    current=c.get(path).json()
    assert current['revision_state'] == 'approved' and current['approved_by'] == ids['reviewer']

def test_review_regression_decision_confirmation_replay_rechecks_revoked_authority(env):
    c,f,app,ids=env;h=login(c);binding,_=evidence(c,ids,h);case=support_case(c,f,ids,h)
    path=base(ids)+f'/support-cases/{case["id"]}/decisions'
    row=post(c,path,h,decision_payload(binding));cmd=expected(row,reason='Checked original')
    path+=f'/{row["id"]}/confirm';post(c,path,h,cmd,200)
    revoke_authority(f,ids,'education_decision.confirm')
    response=c.post(path,headers=h,json=cmd)
    assert response.status_code==403,response.text
    current=c.get(path.rsplit('/confirm',1)[0]).json()
    assert current['content']['state'] == 'confirmed' and current['content']['confirmed_by'] == ids['reviewer']

def test_review_regression_clarification_retry_does_not_release_source_after_evidence_access_loss(env):
    c,f,app,ids=env;h=login(c);binding,_=evidence(c,ids,h);case=support_case(c,f,ids,h)
    path=base(ids)+f'/support-cases/{case["id"]}/clarifications'
    cmd=retry(kind='source_review',description='Synthetic sensitive source description',source=binding)
    row=post(c,path,h,cmd)
    with f.begin() as db:
        for a in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a'])):
            a.actions=[v for v in a.actions if v not in {'evidence.read','evidence.write'}]
    current=c.get(path);assert current.status_code==200,current.text
    assert current.json()['items'][0]['description'] is None
    response=c.post(path,headers=h,json=cmd)
    assert response.status_code==403 or response.json().get('description') is None,response.text

def test_review_regression_profile_history_does_not_release_review_prose_after_source_access_loss(env):
    c,f,app,ids=env;h=login(c);binding,item=evidence(c,ids,h)
    path=base(ids)+f'/learners/{ids["a"]}/support-profile'
    row=post(c,path+'/statements',h,retry(category='support_strategy',content='Synthetic source-derived statement',source=binding,observed_at=(utcnow()-timedelta(days=1)).isoformat()))
    row=post(c,path+f'/statements/{row["id"]}/review',h,expected(row,outcome='confirmed',reason='Synthetic sensitive review detail from original source'),200)
    # The source was linked to the wrong learner. Correct it through public HTTP.
    source=item['source']
    correction={'expected_version':item['version'],'learner_id':ids['b'],'claim_type':'report','reporter':'Synthetic authority','source_type':'imported_document','certainty':'confirmed','occurred_at':(utcnow()-timedelta(days=20)).isoformat(),'topic':'education','content':'Synthetic source belongs to learner B','reason':'Wrong learner corrected','excerpt_page':source['page'],'excerpt_start':source['span_start'],'excerpt_end':source['span_end']}
    post(c,base(ids)+f'/evidence/{item["id"]}/corrections',h,correction,200)
    # An A-only teacher did not author this reason and cannot read B's evidence.
    login(c,'teacher')
    assert c.get(base(ids)+f'/evidence/{item["id"]}').status_code==403
    normal=c.get(path).json()['items'][0]
    assert normal['content'] is None
    assert normal.get('review_reason') is None
    response=c.get(path+f'/statements/{row["id"]}/history')
    assert response.status_code==403 or not response.json()['items'][0].get('reason'),response.text

def test_review_regression_clarification_resolution_does_not_release_prose_after_source_access_loss(env):
    c,f,app,ids=env;h=login(c);binding,_=evidence(c,ids,h);case=support_case(c,f,ids,h)
    path=base(ids)+f'/support-cases/{case["id"]}/clarifications'
    row=post(c,path,h,retry(kind='source_review',description='Synthetic source-derived clarification',source=binding))
    post(c,path+f'/{row["id"]}/resolve',h,expected(row,resolution='Synthetic sensitive finding from original source'),200)
    with f.begin() as db:
        for a in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a'])):
            a.actions=[v for v in a.actions if v not in {'evidence.read','evidence.write'}]
    response=c.get(path);assert response.status_code==200,response.text
    row=response.json()['items'][0];assert row['description'] is None and row['source'] is None
    assert not row.get('resolution'),response.text

def test_review_regression_original_source_revision_invalidates_profile_brief_and_pending_approval(env):
    import json
    from spesped.contexts.evidence.models import SourceItem
    c,f,app,ids=env;h=login(c);binding,item=evidence(c,ids,h)
    path=base(ids)+f'/learners/{ids["a"]}/support-profile'
    statement=post(c,path+'/statements',h,retry(category='support_strategy',content='Synthetic reviewed support',source=binding,observed_at=(utcnow()-timedelta(days=1)).isoformat()))
    post(c,path+f'/statements/{statement["id"]}/review',h,expected(statement,outcome='confirmed',reason='Synthetic source verified'),200)
    row=post(c,base(ids)+f'/learners/{ids["a"]}/education-plans',h,plan_payload(binding))
    planpath=base(ids)+f'/education-plans/{row["id"]}'
    row=post(c,planpath+'/review',h,expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Exact source reviewed'),200)
    with f() as db:
        source=db.get(SourceItem,item['source']['source_id'])
        metadata=retry(external_scope=source.external_scope,external_id=source.external_id,sender=source.sender,document_type=source.document_type,received_at=utcnow().isoformat())
        source_id,source_version=source.id,source.version
    response=c.post(base(ids)+f'/intake/{source_id}/revisions',headers={**h,'X-Expected-Version':str(source_version),'X-Evidence-Filename':'synthetic-revision.txt','X-Evidence-Metadata':json.dumps(metadata)},content=b'Synthetic changed original educational document')
    assert response.status_code==201,response.text
    # The old confirmed EvidenceItem itself has not changed; original revision did.
    assert c.get(path).json()['items'][0]['content'] is None
    result=c.post(planpath+'/approve',headers=h,json=expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Try outdated original'))
    assert result.status_code==409 and result.json()['error']['code']=='source_changed',result.text
    assert c.get(planpath).json()['content'].get('goals') is None
    login(c,'assistant');assert c.get(path+'/brief').json()['items']==[]
    assert c.get(base(ids)+f'/evidence/{item["id"]}').status_code==403

def test_review_regression_late_command_failure_rolls_back_plan_audit_and_outbox(env,monkeypatch):
    import pytest
    from sqlalchemy import func
    from spesped.auth import Actor
    from spesped.errors import DomainError
    from spesped.contexts.identity.models import AuditRecord
    from spesped.contexts.plans import service
    from spesped.contexts.plans.models import IndividualEducationPlan,PlanEvent,PlanCommand,PlanRevision,GoalRevision
    from spesped.contexts.plans.schemas import CreatePlan
    from spesped.contexts.entitlements.common import mutate
    c,f,app,ids=env
    def fail(*args,**kwargs):raise DomainError('synthetic_late_failure','Synthetic transaction failure',409)
    monkeypatch.setattr(service,'remember',fail)
    with f() as db:
        before=db.scalar(select(func.count()).select_from(AuditRecord))
        with pytest.raises(DomainError,match='Synthetic transaction'):
            mutate(db,lambda:service.save_plan(db,Actor(ids['reviewer']),ids['school'],ids['a'],CreatePlan(**plan_payload())))
        assert db.scalar(select(func.count()).select_from(AuditRecord))==before
        for model in (IndividualEducationPlan,PlanEvent,PlanCommand,PlanRevision,GoalRevision):
            assert db.scalar(select(func.count()).select_from(model))==0


def test_referral_submission_replay_rechecks_signer_and_retains_actual_record(env):
    from plans_fixtures import reviewed_referral
    client,factory,app,ids=env;headers=login(client);binding,_=evidence(client,ids,headers);case=support_case(client,factory,ids,headers)
    row,_=reviewed_referral(client,ids,headers,case,binding)
    path=base(ids)+f'/support-cases/{case["id"]}/referrals/{row["id"]}'
    cmd=expected(row,kind='submission',actual_contact=True,occurred_at=(utcnow()-timedelta(minutes=5)).isoformat(),recipient='Synthetic expert service',channel='secure_external_system',external_reference='synthetic-actual-submission',note='Synthetic actually completed external submission',source=binding)
    post(client,path+'/contacts',headers,cmd,200)
    revoke_authority(factory,ids,'support_case.submit')
    assert client.post(path+'/contacts',headers=headers,json=cmd).status_code == 403
    current=client.get(path).json()
    assert current['state'] == 'submitted' and len(current['contacts']) == 1
    assert current['contacts'][0]['actual_contact'] is True
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReferralContact)) == 1
        assert db.scalar(select(func.count()).select_from(EntitlementEvent).where(EntitlementEvent.event_type == 'referral.submission')) == 1


def test_all_sourced_referral_consent_and_clarification_prose_redacted_on_replay_and_history(env):
    from plans_fixtures import reviewed_referral
    from spesped.contexts.entitlements.models import CaseClarification,EducationConsent
    from spesped.contexts.plans.models import ProfileReview
    client,factory,app,ids=env;headers=login(client);binding,item=evidence(client,ids,headers);case=support_case(client,factory,ids,headers)
    row,consents=reviewed_referral(client,ids,headers,case,binding)
    case_path=base(ids)+f'/support-cases/{case["id"]}'
    path=case_path+f'/referrals/{row["id"]}'
    submission=expected(row,kind='submission',actual_contact=True,occurred_at=(utcnow()-timedelta(minutes=5)).isoformat(),recipient='Synthetic expert service',channel='secure_external_system',external_reference='synthetic-submission-proof',note='Synthetic private submission detail',source=binding)
    row=post(client,path+'/contacts',headers,submission,200)
    followup=expected(row,kind='follow_up',actual_contact=False,occurred_at=(utcnow()+timedelta(days=5)).isoformat(),recipient='Synthetic expert service',channel='planned',note='Synthetic private follow-up detail')
    post(client,path+'/contacts',headers,followup,200)
    cmd=retry(kind='source_review',description='Synthetic private clarification detail',source=binding)
    issue=post(client,case_path+'/clarifications',headers,cmd)
    resolve_cmd=expected(issue,resolution='Synthetic private resolution detail')
    post(client,case_path+f'/clarifications/{issue["id"]}/resolve',headers,resolve_cmd,200)
    permission=consents['disclosure_permission']
    revoke_cmd=expected(permission,reason='Synthetic private withdrawal detail')
    post(client,case_path+f'/consents/{permission["id"]}/revoke',headers,revoke_cmd,200)
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id == ids['reviewer'],StaffAssignment.learner_id == ids['a'])):
            assignment.actions=[a for a in assignment.actions if a not in {'evidence.read','evidence.write'}]
    # All responses share the same current actor-aware projection. Retries must
    # not restore prose through a different serializer or echo its submitted body.
    for response in [client.get(path),client.post(path+'/contacts',headers=headers,json=followup)]:
        assert response.status_code == 200,response.text
        value=response.json();assert 'concern' not in value['content']
        assert all(c['note'] is None and c['recipient'] is None and c['source'] is None for c in value['contacts'])
    history=client.get(path+'/revisions').json()
    assert 'concern' not in history['items'][0]['content']
    for response in [client.get(case_path+'/clarifications'),client.post(case_path+'/clarifications',headers=headers,json=cmd),client.post(case_path+f'/clarifications/{issue["id"]}/resolve',headers=headers,json=resolve_cmd)]:
        assert response.status_code in {200,201},response.text
        value=response.json();values=value.get('items',[value])
        assert all(v['source'] is None and v['description'] is None and v['resolution'] is None for v in values)
    for response in [client.get(case_path+'/consents'),client.post(case_path+f'/consents/{permission["id"]}/revoke',headers=headers,json=revoke_cmd)]:
        value=response.json();values=value.get('items',[value])
        assert all(v['source'] is None and v['purpose'] is None and v['representative'] is None and v['representative_capacity'] is None and v['revoked_reason'] is None for v in values)
    with factory() as db:
        assert db.get(CaseClarification,issue['id']).resolution == resolve_cmd['resolution']
        assert db.get(EducationConsent,permission['id']).revoked_reason == revoke_cmd['reason']


def test_postgres_revision_and_review_serialize_in_pupil_then_plan_order(env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event,local
    from sqlalchemy import event
    from spesped.contexts.plans import service
    from spesped.contexts.plans.schemas import RevisePlan,PlanLifecycle
    from spesped.contexts.entitlements.common import mutate
    from spesped.errors import DomainError
    client,factory,app,ids=env
    if factory.kw['bind'].dialect.name != 'postgresql':pytest.skip('Real PostgreSQL row-lock interleaving')
    headers=login(client);payload=plan_payload();row=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',headers,payload)
    revised={**payload,'request_key':key(),'expected_version':row['version']};revised.pop('kind')
    commands={'revision':RevisePlan(**revised),'review':PlanLifecycle(**expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Concurrent exact review'))}
    first_locked=Event();peer_attempted=Event();thread=local();orders={'review':[],'revision':[]};engine=factory.kw['bind']
    def before(conn,cursor,statement,parameters,context,executemany):
        mode=getattr(thread,'mode',None)
        if mode and 'FOR UPDATE' in statement:
            table='pupil' if 'FROM identity_learners' in statement else 'plan' if 'FROM plans_individual_education_plans' in statement else None
            if table:
                orders[mode].append(table)
                if mode == 'revision' and table == 'pupil':peer_attempted.set()
    def after(conn,cursor,statement,parameters,context,executemany):
        if getattr(thread,'mode',None) == 'review' and 'FROM identity_learners' in statement and 'FOR UPDATE' in statement:
            first_locked.set()
            assert peer_attempted.wait(10),'Second real transaction never attempted the held pupil lock'
    event.listen(engine,'before_cursor_execute',before);event.listen(engine,'after_cursor_execute',after)
    def run(mode):
        thread.mode=mode
        try:
            with factory() as db:
                if mode == 'revision':
                    assert first_locked.wait(10)
                    mutate(db,lambda:service.save_plan(db,Actor(ids['reviewer']),ids['school'],ids['a'],commands[mode],row['id']))
                else:mutate(db,lambda:service.lifecycle(db,Actor(ids['reviewer']),ids['school'],row['id'],commands[mode],'review'))
            return 'committed'
        except DomainError as exc:return exc.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            review=pool.submit(run,'review');revision=pool.submit(run,'revision')
            results=[review.result(20),revision.result(20)]
    finally:
        event.remove(engine,'before_cursor_execute',before);event.remove(engine,'after_cursor_execute',after)
    assert results == ['committed',409]
    assert orders['review'][:2] == ['pupil','plan'] and orders['revision'][:2] == ['pupil','plan']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PlanRevision)) == 1
        assert db.get(IndividualEducationPlan,row['id']).state == 'in_review'
        assert db.scalar(select(func.count()).select_from(PlanEvent).where(PlanEvent.event_type == 'plan.revision_created')) == 1


def test_actual_postgres_deadlock_is_safe_retry_and_rolls_back_audit_outbox_and_receipt(env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from spesped.audit import record_audit
    from spesped.contexts.plans.models import PlanCommand
    from spesped.contexts.entitlements.common import mutate
    from spesped.errors import DomainError
    client,factory,app,ids=env
    if factory.kw['bind'].dialect.name != 'postgresql':pytest.skip('Actual PostgreSQL SQLSTATE40P01 and transaction rollback')
    barrier=Barrier(2)
    def run(first,second):
        with factory() as db:
            try:
                def operation():
                    db.scalar(select(Learner).where(Learner.id == ids[first]).with_for_update())
                    record_audit(db,Actor(ids['reviewer']),ids['school'],'synthetic.deadlock_probe','learner',ids[first])
                    db.add(PlanEvent(school_id=ids['school'],aggregate_id=ids[first],aggregate_version=1,event_type='synthetic.deadlock_probe',payload={}))
                    db.add(PlanCommand(school_id=ids['school'],actor_id=ids['reviewer'],request_key='synthetic-deadlock-'+first,digest='a'*64,operation='synthetic.deadlock_probe',target_id=ids[first]))
                    db.flush();barrier.wait(timeout=10)
                    db.scalar(select(Learner).where(Learner.id == ids[second]).with_for_update())
                mutate(db,operation)
                return 'committed'
            except DomainError as exc:
                assert exc.status_code == 409 and exc.code == 'revision_conflict'
                assert not db.in_transaction()
                assert 'Retry with the same request key' in exc.message
                return 'controlled409'
    with ThreadPoolExecutor(max_workers=2) as pool:
        left=pool.submit(run,'a','b');right=pool.submit(run,'b','a');results=[left.result(20),right.result(20)]
    assert sorted(results) == ['committed','controlled409']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PlanEvent).where(PlanEvent.event_type == 'synthetic.deadlock_probe')) == 1
        assert db.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action == 'synthetic.deadlock_probe')) == 1
        assert db.scalar(select(func.count()).select_from(PlanCommand).where(PlanCommand.operation == 'synthetic.deadlock_probe')) == 1


def test_unrelated_database_error_is_not_misclassified_as_retry_conflict(env):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from spesped.contexts.entitlements.common import mutate
    client,factory,app,ids=env
    with factory() as db:
        def operation():
            db.add(PlanEvent(school_id=ids['school'],aggregate_id=ids['a'],aggregate_version=1,event_type='synthetic.nonretryable_probe',payload={}))
            db.flush()
            db.execute(text('SELECT * FROM synthetic_relation_that_does_not_exist'))
        with pytest.raises(DBAPIError):mutate(db,operation)
        assert not db.in_transaction()
        assert db.scalar(select(func.count()).select_from(PlanEvent).where(PlanEvent.event_type == 'synthetic.nonretryable_probe')) == 0


def test_recommendation_clarification_resolution_also_tracks_its_decision_source(env):
    client,factory,app,ids=env;headers=login(client)
    expert_binding,_=evidence(client,ids,headers,text='Synthetic expert recommendation source')
    decision_binding,decision_item=evidence(client,ids,headers,text='Synthetic separate authority decision source')
    case=support_case(client,factory,ids,headers);path=base(ids)+f'/support-cases/{case["id"]}'
    dates=period()
    assessment=post(client,path+'/expert-assessments',headers,retry(issuer='Synthetic expert authority',assessment_at=(utcnow()-timedelta(days=70)).isoformat(),source=expert_binding,recommendations=[{'category':'individually_adapted_education','subject':'reading','content':'Synthetic expert recommendation','amount':'150','unit':'hours','counting_basis':'learner_time','source':expert_binding,**dates}]))
    post(client,path+f'/expert-assessments/{assessment["id"]}/confirm',headers,expected(assessment,reason='Checked expert original'),200)
    decision=confirmed_decision(client,ids,headers,case,decision_binding)
    issue=client.get(path+'/clarifications').json()['items'][0]
    assert issue['kind'] == 'recommendation_difference'
    post(client,path+f'/clarifications/{issue["id"]}/resolve',headers,expected(issue,resolution='Synthetic private detail from the separate decision source'),200)
    source=decision_item['source']
    correction={'expected_version':decision_item['version'],'learner_id':ids['b'],'claim_type':'report','reporter':'Synthetic authority','source_type':'imported_document','certainty':'confirmed','occurred_at':(utcnow()-timedelta(days=20)).isoformat(),'topic':'education','content':'Synthetic decision source belongs to pupil B','reason':'Correct wrong pupil association','excerpt_page':source['page'],'excerpt_start':source['span_start'],'excerpt_end':source['span_end']}
    post(client,base(ids)+f'/evidence/{decision_item["id"]}/corrections',headers,correction,200)
    # Even the A+B reviewer cannot treat a B-bound source as an A case source.
    issue=client.get(path+'/clarifications').json()['items'][0]
    assert issue['source_status'] == 'review_required'
    assert issue['description'] is None and issue['resolution'] is None and issue['source'] is None
