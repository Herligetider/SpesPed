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
from spesped.contexts.identity.models import AuditRecord,AuthorityGrant,Learner
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
