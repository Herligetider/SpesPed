from sqlalchemy import select,func
import pytest
from plan_generation_fixtures import generated_env,plan_wire,env,post,generate,proposal,selection,manual
from plans_fixtures import base,retry,expected,login,key,activate
from spesped.contexts.plans.models import PlanRevision,GoalRevision,PlanCommand,PlanProposalReview,PlanEvent
from spesped.contexts.identity.models import AuthorityGrant,AuditRecord
from spesped.contexts.evidence.models import Derivative
from spesped.contexts.plans import service


def path(e):return base(e.ids)+f'/education-plans/{e.plan["id"]}'


def test_actual_local_proposal_selection_preserves_manual_text_and_activation(generated_env):
    e=generated_env;job=generate(e);assert job['state'] == 'succeeded',job
    p=proposal(e,job);assert p['unconfirmed'] and p['source_manifest'][0]['reference']['source_id'] == e.basis['id']
    command=selection(e,p)
    row=post(e.client,path(e)+'/suggestion-reviews',e.h,command,200)
    assert row['revision_state'] == 'draft' and row['active_revision_id'] is None and row['approved_at'] is None
    assert row['content']['title'] == e.wire.title
    assert row['content']['goals'][0]['expected_action'] == e.plan['content']['goals'][0]['expected_action']
    for field in ('participation_record','allocations','contributions','effective_from','effective_until'):
        before=e.plan['content'][field];after=row['content'][field]
        if isinstance(before,list):before=[{k:v for k,v in r.items() if k != 'id'} for r in before];after=[{k:v for k,v in r.items() if k != 'id'} for r in after]
        assert before == after
    assert row['content']['generation_lineage']['title']['job_id'] == job['id']
    again=post(e.client,path(e)+'/suggestion-reviews',e.h,command,200);assert again['content']['id'] == row['content']['id']
    # Activation remains a separate exact human review/approval workflow.
    active=activate(e.client,e.ids,e.h,row);assert active['active_revision_id'] == row['content']['id']
    assert len(e.wire.requests) == 2  # evaluated release + actual local execution


def test_new_goal_dates_and_curriculum_are_human_selected(generated_env):
    e=generated_env;e.wire.target=None;job=generate(e);p=proposal(e,job)
    command=selection(e,p);command.update(selected_fields=[],selected_goal_keys=['reading'])
    assert e.client.post(path(e)+'/suggestion-reviews',headers=e.h,json=command).status_code == 422
    command['new_goals']=[{'proposal_key':'reading','curriculum_reference':'Human reviewed synthetic curriculum','effective_from':e.plan['content']['effective_from'],'effective_until':e.plan['content']['effective_until']}]
    from datetime import datetime,timedelta
    command['new_goals'][0]['effective_until']=(datetime.fromisoformat(e.plan['content']['effective_until'])+timedelta(days=1)).isoformat()
    assert e.client.post(path(e)+'/suggestion-reviews',headers=e.h,json=command).status_code == 422
    command['new_goals'][0]['effective_until']=e.plan['content']['effective_until']
    row=post(e.client,path(e)+'/suggestion-reviews',e.h,command,200)
    assert len(row['content']['goals']) == 2
    new=next(g for g in row['content']['goals'] if g['goal_id'] != e.plan['content']['goals'][0]['goal_id'])
    assert new['curriculum_reference'] == 'Human reviewed synthetic curriculum'
    assert row['content']['participation_record'] == e.plan['content']['participation_record']


@pytest.mark.parametrize('mode',['rights','unknown_source','foreign_goal','unavailable'])
def test_invalid_output_foreign_goal_and_failure_keep_manual_editor(generated_env,mode):
    e=generated_env;e.wire.mode=mode;job=generate(e)
    response=e.client.get(path(e)+f'/suggestions/{job["id"]}',params={'basis_id':e.basis['id']})
    assert response.status_code == 409,response.text
    if mode != 'foreign_goal':assert job['state'] != 'succeeded'
    current=e.client.get(path(e)).json();assert current['content']['id'] == e.plan['content']['id']
    assert current['content']['title'] == e.plan['content']['title']


def test_regeneration_never_overwrites_manual_revision_and_exact_selection_is_stale(generated_env):
    e=generated_env;job=generate(e);p=proposal(e,job)
    edited=post(e.client,path(e)+'/revisions',e.h,manual(e,e.plan,title='Human edited while model suggestion was open'))
    assert e.client.post(path(e)+'/suggestion-reviews',headers=e.h,json=selection(e,p)).status_code == 409
    assert e.client.post(path(e)+'/suggestions',headers=e.h,json=retry(basis_id=e.basis['id'],policy_id=e.policy,release_id=e.release)).status_code == 409
    assert e.client.get(path(e)).json()['content']['title'] == edited['content']['title']


@pytest.mark.parametrize('outcome',['rejected','discarded'])
def test_reject_discard_and_replay_do_not_make_a_revision(generated_env,outcome):
    e=generated_env;p=proposal(e,generate(e));command=selection(e,p);command.update(outcome=outcome,selected_fields=[])
    row=post(e.client,path(e)+'/suggestion-reviews',e.h,command,200);assert row['content']['id'] == e.plan['content']['id']
    assert post(e.client,path(e)+'/suggestion-reviews',e.h,command,200)['content']['id'] == e.plan['content']['id']
    assert e.client.get(path(e)+f'/suggestions/{p["job_id"]}',params={'basis_id':e.basis['id']}).status_code == 409
    conflicting={**command,'request_key':key(),'outcome':'applied','selected_fields':['title']}
    assert e.client.post(path(e)+'/suggestion-reviews',headers=e.h,json=conflicting).status_code == 409


def test_processing_recall_hides_generated_history_preserves_lineage_until_explicit_human_replacement(generated_env):
    e=generated_env;p=proposal(e,generate(e));row=post(e.client,path(e)+'/suggestion-reviews',e.h,selection(e,p),200)
    row=post(e.client,path(e)+'/revisions',e.h,manual(e,row,title='Human edit remains derived'))
    assert row['content']['generation_lineage']['title']['job_id'] == p['job_id']
    unchanged=manual(e,row,sever_generation_fields=['title'])
    assert e.client.post(path(e)+'/revisions',headers=e.h,json=unchanged).status_code == 422
    independent=manual(e,row,title='Independently authored replacement',sever_generation_fields=['title'])
    independent=post(e.client,path(e)+'/revisions',e.h,independent)
    assert not independent['content'].get('generation_lineage')
    release=next(r for r in e.client.get(base(e.ids)+'/ai/configuration').json()['releases']['items'] if r['id'] == e.release)
    post(e.client,base(e.ids)+f'/ai/configuration/release/{e.release}/revoke',e.h,{'expected_version':release['version']},200)
    history=e.client.get(path(e)+'/revisions').json()['items']
    assert history[0]['content']['title'] == 'Independently authored replacement'
    assert history[1]['source_status'] == 'review_required' and 'title' not in history[1]['content']
    assert history[2]['source_status'] == 'review_required'
    assert history[3]['content']['title'] == e.plan['content']['title']
    reviews=e.client.get(path(e)+'/suggestion-reviews').json()['items']
    assert reviews[0]['reason'] is None and reviews[0]['source_status'] == 'review_required'


def test_original_source_correction_hides_generated_text_and_reauthorizes_replay(generated_env):
    e=generated_env;p=proposal(e,generate(e));command=selection(e,p);post(e.client,path(e)+'/suggestion-reviews',e.h,command,200)
    item=e.expert_item
    corrected={'expected_version':item['version'],'learner_id':e.ids['b'],'claim_type':'report','reporter':'Synthetic authority','source_type':'imported_document','certainty':'confirmed','occurred_at':item['occurred_at'],'topic':'education','content':'Corrected synthetic pupil association','reason':'Original source belonged to pupil B','excerpt_page':item['source']['page'],'excerpt_start':item['source']['span_start'],'excerpt_end':item['source']['span_end']}
    post(e.client,base(e.ids)+f'/evidence/{item["id"]}/corrections',e.h,corrected,200)
    current=e.client.get(path(e));assert current.status_code == 200,current.text
    assert current.json()['source_status'] == 'review_required' and 'title' not in current.json()['content']
    assert e.client.post(path(e)+'/suggestion-reviews',headers=e.h,json=command).status_code == 409
    assert e.client.get(base(e.ids)+f'/plan-generation-bases/{e.basis["id"]}').status_code == 409
    assert e.client.get(path(e)+'/suggestion-reviews').json()['items'][0]['reason'] is None


def test_source_and_ai_rights_revocation_cross_school_and_rollback(generated_env,monkeypatch):
    e=generated_env;job=generate(e);p=proposal(e,job)
    assert e.client.get(f'/api/v1/schools/{e.ids["other_school"]}/plan-generation-bases/{e.basis["id"]}').status_code == 403
    login(e.client,'assistant');assert e.client.get(path(e)+f'/suggestions/{job["id"]}',params={'basis_id':e.basis['id']}).status_code == 403
    e.h=login(e.client)
    with e.factory() as db:before=tuple(db.scalar(select(func.count()).select_from(model)) for model in (PlanRevision,GoalRevision,PlanCommand,PlanProposalReview,PlanEvent,AuditRecord,Derivative))
    original=service.event
    def fail(*args,**kwargs):raise RuntimeError('synthetic late transaction failure')
    monkeypatch.setattr(service,'event',fail)
    command=selection(e,p)
    with pytest.raises(RuntimeError):e.client.post(path(e)+'/suggestion-reviews',headers=e.h,json=command)
    with e.factory() as db:after=tuple(db.scalar(select(func.count()).select_from(model)) for model in (PlanRevision,GoalRevision,PlanCommand,PlanProposalReview,PlanEvent,AuditRecord,Derivative))
    assert before == after
    monkeypatch.setattr(service,'event',original)
    post(e.client,path(e)+'/suggestion-reviews',e.h,command,200)
    with e.factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id == e.ids['reviewer'],AuthorityGrant.action == 'ai.iep_drafting')):grant.state='revoked'
    assert e.client.post(path(e)+'/suggestion-reviews',headers=e.h,json=command).status_code == 403


def test_curated_generation_metadata_has_no_source_permission_and_preserves_pending_writes(generated_env):
    from spesped.contexts.plans.projections import generation_bindings_are_current
    from spesped.contexts.entitlements.models import ExpertAssessment
    from spesped.contexts.identity.models import StaffAssignment
    from sqlalchemy import event
    e=generated_env;p=proposal(e,generate(e));row=post(e.client,path(e)+'/suggestion-reviews',e.h,selection(e,p),200)
    lineage=row['content']['generation_lineage']
    with e.factory() as db:
        assert generation_bindings_are_current(db,e.ids['school'],e.ids['a'],lineage,e.runtime)
        assert not generation_bindings_are_current(db,e.ids['school'],e.ids['b'],lineage,e.runtime)
        assert not generation_bindings_are_current(db,e.ids['school'],e.ids['a'],lineage,None)
        assessment=db.get(ExpertAssessment,e.assessment['id']);assessment.state='disputed'
        writes=[]
        def flushed(*_):writes.append(True)
        event.listen(db,'before_flush',flushed)
        assert not generation_bindings_are_current(db,e.ids['school'],e.ids['a'],lineage,e.runtime)
        assert assessment.state == 'disputed' and not writes
        db.rollback()
    # Currency cannot replace original evidence/case permission for stored prose.
    with e.factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id == e.ids['reviewer'])):
            assignment.actions=[a for a in assignment.actions if a != 'evidence.read']
    response=e.client.get(path(e))
    assert response.status_code == 403 or (response.status_code == 200 and 'title' not in response.json()['content'])
    response=e.client.get(path(e)+'/suggestion-reviews')
    assert response.status_code == 200 and response.json()['items'][0]['reason'] is None


def test_forward_generation_migration_preserves_manual_legacy_revision_digest(generated_env):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    e=generated_env
    cfg=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    cfg.attributes['database_url']=e.factory.kw['bind'].url.render_as_string(hide_password=False)
    # No generated result has been applied. The populated human-authored plan
    # represents a legacy revision whose existing approved hash must stay valid.
    checks={c['sqltext'] for c in inspect(e.factory.kw['bind']).get_check_constraints('plans_revisions')}
    command.downgrade(cfg,'j06_teaching')
    assert {c['sqltext'] for c in inspect(e.factory.kw['bind']).get_check_constraints('plans_revisions')} == checks
    assert 'generation_lineage' not in {c['name'] for c in inspect(e.factory.kw['bind']).get_columns('plans_revisions')}
    command.upgrade(cfg,'heads')
    assert {c['sqltext'] for c in inspect(e.factory.kw['bind']).get_check_constraints('plans_revisions')} == checks
    result=e.client.get(path(e));assert result.status_code == 200,result.text
    assert result.json()['content_digest'] == e.plan['content_digest']
    assert result.json()['content']['title'] == e.plan['content']['title']
    assert 'generation_lineage' not in result.json()['content']
    from alembic.migration import MigrationContext
    from alembic.autogenerate import compare_metadata
    from spesped.db import Base
    def include(obj,name,type_,reflected,compare_to):return type_ != 'table' or name.startswith('plans_')
    with e.factory.kw['bind'].connect() as connection:
        context=MigrationContext.configure(connection,opts={'include_object':include,'compare_type':True})
        assert compare_metadata(context,Base.metadata) == []


def test_regenerated_draft_preserves_active_revision_and_ancestor_model_lineage(generated_env):
    from spesped.contexts.plans.projections import generation_bindings_are_current
    e=generated_env;p=proposal(e,generate(e))
    first=post(e.client,path(e)+'/suggestion-reviews',e.h,selection(e,p),200)
    active=activate(e.client,e.ids,e.h,first);e.plan=active
    e.basis=post(e.client,path(e)+'/generation-bases',e.h,expected(active,plan_revision_id=active['content']['id'],assessment_ids=[e.assessment['id']],profile_statement_ids=[e.statement['id']]))
    e.wire.title='Synthetic regenerated title after human activation'
    newer=proposal(e,generate(e))
    draft=post(e.client,path(e)+'/suggestion-reviews',e.h,selection(e,newer),200)
    assert draft['revision_state'] == 'draft'
    assert draft['active_revision_id'] == active['active_revision_id']
    assert draft['content']['generation_lineage']['title']['job_id'] != first['content']['generation_lineage']['title']['job_id']
    with e.factory() as db:
        assert generation_bindings_are_current(db,e.ids['school'],e.ids['a'],draft['content']['generation_lineage'],e.runtime)


def test_generated_revision_of_import_retains_original_approval_only_on_imported_predecessor(generated_env):
    from spesped.db import utcnow
    from datetime import timedelta
    e=generated_env
    original={'approver':'Synthetic original authority','authority':'Synthetic imported approval record','approved_at':(utcnow()-timedelta(days=1)).isoformat(),'source':e.plan['content']['sources'][0]}
    imported=post(e.client,path(e)+'/revisions',e.h,manual(e,e.plan,origin='imported',original_approval=original))
    e.plan=imported
    e.basis=post(e.client,path(e)+'/generation-bases',e.h,expected(imported,plan_revision_id=imported['content']['id'],assessment_ids=[e.assessment['id']],profile_statement_ids=[e.statement['id']]))
    p=proposal(e,generate(e));draft=post(e.client,path(e)+'/suggestion-reviews',e.h,selection(e,p),200)
    assert draft['content']['origin'] == 'authored' and draft['content']['original_approval'] is None
    assert draft['approved_at'] is None and draft['active_revision_id'] is None
    history=e.client.get(path(e)+'/revisions').json()['items']
    previous=next(r for r in history if r['content']['id'] == imported['content']['id'])
    assert previous['content']['origin'] == 'imported' and previous['content']['original_approval'] == imported['content']['original_approval']
