from datetime import date,timedelta
import json
from uuid import uuid4
import pytest
from sqlalchemy import select,func,text,create_engine
from sqlalchemy.orm.exc import StaleDataError
from alembic import command
from alembic.config import Config
from pathlib import Path
from curriculum_fixtures import curriculum_env,teaching_env,env,login,path,resource,resource_content,share,scheme,plan_content,class_plan,publish,source,ordinary_goal,basis,session,actual
from plans_fixtures import retry,expected,base,key,evidence
from spesped.contexts.curriculum import models as m
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment,AuditRecord
from spesped.db import utcnow


def test_private_search_current_rights_and_real_session_security(curriculum_env):
    client,factory,app,ids=curriculum_env;h=login(client)
    payload=retry(content=resource_content());response=client.post(path(ids)+'/resources',headers=h,json=payload)
    assert response.status_code==201,response.text
    row=response.json();assert row['visibility']=='private' and row['suitability']=='human_confirmation_required'
    assert client.post(path(ids)+'/resources',headers=h,json=payload).json()==row
    payload['content']['title']='Conflicting data'
    assert client.post(path(ids)+'/resources',headers=h,json=payload).status_code==409
    assert client.get(path(ids)+f'/resource-revisions/{row["revision_id"]}?purpose=ai').status_code==403
    login(client,'teacher')
    assert client.get(path(ids)+'/resources').json()=={'items':[],'total':0}
    assert client.get(path(ids)+f'/resources/{row["id"]}').status_code==403
    h=login(client);row=share(client,ids,h,row)
    login(client,'teacher')
    result=client.get(path(ids)+'/resources?subject=mathematics&skill=counting&age=8&duration_max=40&group_size=2&tag=beads').json()
    assert result['total']==1 and 'skill' in result['items'][0]['match_reasons']
    assert client.get(path(ids)+'/resources?age=15').json()['total']==0
    assert client.get(path(ids)+'/resources?offset=1&limit=1').json()['items']==[]
    for who in ('guardian','tech'):
        login(client,who)
        assert client.get(path(ids)+'/resources').status_code==403
    h=login(client)
    assert client.post(path(ids)+'/resources',json=retry(content=resource_content())).status_code==403
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.CommandReceipt))==2
        assert db.scalar(select(func.count()).select_from(m.CurriculumEvent))==2
        event=db.scalar(select(m.CurriculumEvent).where(m.CurriculumEvent.event_type=='curriculum.resource.created'))
        assert event.schema_version==1 and event.correlation_id and event.causation_id==payload['request_key']
        assert event.occurred_at.tzinfo is not None and event.recorded_at.tzinfo is not None
        assert db.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action.like('curriculum.%')))==2


def test_native_dated_team_sharing_exact_revision_and_variants(curriculum_env):
    client,factory,app,ids=curriculum_env;h=login(client);row=resource(client,ids,h)
    response=client.post(path(ids)+'/resource-teams',headers=h,json=retry(name='Synthetic team'));assert response.status_code==201,response.text
    team=response.json()
    for name in ('reviewer','teacher'):
        response=client.post(path(ids)+f'/resource-teams/{team["id"]}/membership',headers=h,json=expected(team,user_id=ids[name],valid_from='2026-01-01',valid_until='2027-12-31',state='active'));assert response.status_code==200,response.text
        team=response.json()
    row=share(client,ids,h,row,'team',team_id=team['id'])
    login(client,'teacher');assert client.get(path(ids)+f'/resources/{row["id"]}').status_code==200
    h=login(client)
    response=client.post(path(ids)+'/resources',headers=h,json=retry(content=resource_content(duration_minutes=15),original_revision_id=row['revision_id'],changes=['Shortened practice to fifteen minutes']))
    assert response.status_code==201,response.text
    variant=response.json();assert variant['original_revision_id']==row['revision_id'] and variant['changes']==['Shortened practice to fifteen minutes']
    assert variant['original_provenance']==row['original_provenance']
    assert {'field':'duration_minutes','original':30,'current':15} in variant['field_changes']
    bad=client.post(path(ids)+'/resources',headers=h,json=retry(content=resource_content(original_provenance='Changed invented original'),original_revision_id=row['revision_id'],changes=['Changed origin']))
    assert bad.status_code==409
    response=client.post(path(ids)+f'/resources/{row["id"]}/revisions',headers=h,json=expected(row,content=resource_content(duration_minutes=20),changes=['Shorter presentation']))
    assert response.status_code==201,response.text
    revised=response.json();assert revised['visibility']=='private' and revised['previous_revision_id']==row['revision_id']
    login(client,'teacher')
    assert client.get(path(ids)+f'/resource-revisions/{row["revision_id"]}').status_code==403
    assert client.get(path(ids)+f'/resources/{revised["id"]}').status_code==403
    h=login(client);revised=share(client,ids,h,revised,'team',team_id=team['id'])
    # Exact sharing includes its same-resource immutable history and visible changes.
    login(client,'teacher');shared=client.get(path(ids)+f'/resources/{revised["id"]}')
    assert shared.status_code==200,shared.text
    assert shared.json()['originals'][0]['revision_id']==row['revision_id']
    h=login(client)
    response=client.post(path(ids)+f'/resource-teams/{team["id"]}/membership',headers=h,json=expected(team,user_id=ids['teacher'],valid_from='2026-01-01',valid_until='2027-12-31',state='revoked'));assert response.status_code==200
    login(client,'teacher');assert client.get(path(ids)+f'/resources/{row["id"]}').status_code==403


def test_material_inventory_unknown_and_reservation_contract(curriculum_env):
    client,factory,app,ids=curriculum_env;h=login(client)
    content={'title':'Synthetic bead tray','material_type':'beads','location':'Synthetic shelf A','count':None,'inventory_checked_on':None,'presentation_revision_ids':[]}
    response=client.post(path(ids)+'/materials',headers=h,json=retry(content=content));assert response.status_code==201,response.text
    row=response.json();assert row['count'] is None and row['availability']=='unknown'
    req={'school_id':ids['school'],'material_id':row['id'],'material_version':row['version'],'count':1,'starts_at':utcnow().isoformat(),'ends_at':(utcnow()+timedelta(hours=1)).isoformat()}
    response=client.post(path(ids)+'/material-availability',headers=h,json=req);assert response.status_code==200,response.text
    assert response.json()['state']=='unavailable'
    content.update(count=2,inventory_checked_on=date.today().isoformat())
    response=client.patch(path(ids)+f'/materials/{row["id"]}',headers=h,json=expected(row,content=content));assert response.status_code==200,response.text
    assert client.post(path(ids)+'/material-availability',headers=h,json=req).status_code==409
    req['material_version']=response.json()['version']
    class WrongPort:
        def availability(self,db,actor,request):
            from spesped.contexts.curriculum.ports import MaterialAvailability
            return MaterialAvailability(request=request,state='available',available_count=999,checked_at=utcnow(),reservation_revision='synthetic-v1')
    app.state.curriculum_material_reservation_port=WrongPort()
    assert client.post(path(ids)+'/material-availability',headers=h,json=req).status_code==409
    content['count']=-1
    assert client.patch(path(ids)+f'/materials/{row["id"]}',headers=h,json=expected(row,content=content)).status_code==422


@pytest.mark.parametrize('pedagogy',['public','montessori'])
def test_reviewed_scheme_mixed_age_class_plan_and_retained_import(curriculum_env,pedagogy):
    client,factory,app,ids=curriculum_env;h=login(client);sc,sc_content=scheme(client,ids,h,pedagogy)
    assert sc['content']['pedagogy']==pedagogy and sc['content']['reviewed_by']==ids['reviewer']
    assert sc['assessment']['rules'][0]['scale_description']=='Narrative without numeric grade'
    ref,_=source(client,ids,h,'Synthetic unstructured half-year plan retained')
    content=plan_content(sc,themes=[],imported_sources=[ref],import_notes='Periods require manual entry')
    row=class_plan(client,ids,h,content)
    bad=client.post(path(ids)+f'/class-plans/{row["id"]}/publish',headers=h,json=expected(row,revision_id=row['content']['id'],content_digest=row['content']['content_digest'],periods_checked=True,references_checked=True,reason='Unchecked import'))
    assert bad.status_code==409
    content=plan_content(sc,imported_sources=[ref]);response=client.post(path(ids)+f'/class-plans/{row["id"]}/revisions',headers=h,json=expected(row,content=content));assert response.status_code==201,response.text
    row=publish(client,ids,h,response.json())
    context=client.get(path(ids)+f'/class-context/{row["content"]["id"]}?on_date=2026-10-21').json()
    assert context['age_min']==6 and context['age_max']==12 and context['bindings']==[]
    assert context['themes'][0]['title']=='Continents'
    assert client.get(path(ids)+f'/class-context/{row["content"]["id"]}?on_date=2027-07-01').status_code==409
    old_digest=row['content']['content_digest']
    with factory() as db:
        saved=db.get(m.ClassPlanRevision,row['content']['id']);saved.themes=[]
        with pytest.raises(ValueError):db.commit()
    assert client.get(path(ids)+f'/class-plans/{row["id"]}').json()['content']['content_digest']==old_digest


def test_explicit_theme_binding_uses_live_goal_source_and_private_scope(curriculum_env):
    client,factory,app,ids=curriculum_env;h=login(client)
    goal,_=ordinary_goal(client,ids,h);sc,_=scheme(client,ids,h);content=plan_content(sc);row=publish(client,ids,h,class_plan(client,ids,h,content))
    ref,_=source(client,ids,h)
    payload=retry(plan_revision_id=row['content']['id'],theme_id=content['themes'][0]['id'],learner_id=ids['a'],goal_revision_id=goal,participation='adapt',rationale='Shared theme, separate reading goal',adaptation='Read a short continent label with support',materials=['Adapted large-print cards'],sources=[ref])
    response=client.post(path(ids)+'/theme-goal-bindings',headers=h,json=payload);assert response.status_code==201,response.text
    bound=response.json();assert bound['goal_revision_id']==goal and bound['bound_by']==ids['reviewer']
    response=client.get(path(ids)+f'/class-context/{row["content"]["id"]}?on_date=2026-10-21&learner_id={ids["a"]}');assert response.status_code==200,response.text
    assert response.json()['bindings'][0]['materials']==['Adapted large-print cards']
    payload.update(request_key=key(),learner_id=ids['b'])
    assert client.post(path(ids)+'/theme-goal-bindings',headers=h,json=payload).status_code==403
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a'])):assignment.state='revoked'
    assert client.get(path(ids)+f'/theme-goal-bindings?learner_id={ids["a"]}').status_code==403


def test_native_original_digest_correction_and_derived_access(curriculum_env):
    client,factory,app,ids=curriculum_env;h=login(client);ref,original=source(client,ids,h)
    row=resource(client,ids,h,sources=[ref])
    assert row['authorized_originals'][0]['original_digest']==ref['digest']
    invalid={**ref,'digest':'0'*64}
    assert client.post(path(ids)+'/resources',headers=h,json=retry(content=resource_content(sources=[invalid]))).status_code==409
    variant=client.post(path(ids)+'/resources',headers=h,json=retry(content=resource_content(),original_revision_id=row['revision_id'],changes=['Shorter practice']))
    assert variant.status_code==201,variant.text
    # Replace via the real intake versioning API, retaining the prior original.
    metadata=retry(external_scope='synthetic_curriculum',external_id=client.get(base(ids)+f'/intake/{original["id"]}').json().get('external_id','unused'),sender='Synthetic school professional',document_type='curriculum',received_at=utcnow().isoformat())
    from spesped.contexts.evidence.models import SourceItem
    with factory() as db:metadata['external_id']=db.get(SourceItem,original['id']).external_id
    response=client.post(base(ids)+f'/intake/{original["id"]}/revisions',content=b'Synthetic corrected school source',headers={**h,'X-Evidence-Filename':'corrected.txt','X-Evidence-Metadata':json.dumps(metadata),'X-Expected-Version':str(original['version'])})
    assert response.status_code==201,response.text
    assert client.get(path(ids)+f'/resources/{row["id"]}').status_code==409
    assert client.get(path(ids)+f'/resources/{variant.json()["id"]}').status_code==409
    assert client.get(path(ids)+'/resources').json()['total']==0


def test_future_impact_owner_decisions_do_not_mutate_actuals(curriculum_env):
    client,factory,app,ids=curriculum_env;h=login(client);goal,_=ordinary_goal(client,ids,h);sc,_=scheme(client,ids,h)
    content=plan_content(sc);row=publish(client,ids,h,class_plan(client,ids,h,content))
    planned=session(client,ids,h,basis(client,ids,h,{'a':goal}));actual_response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual(ids,{'a':goal})))
    assert actual_response.status_code==201,actual_response.text
    actual_before=actual_response.json()
    app.state.curriculum_future_session_port.dependencies[row['content']['id']]=[planned['revision_id']]
    moved=json.loads(json.dumps(content));moved['themes'][0]['valid_from']='2026-11-01'
    response=client.post(path(ids)+f'/class-plans/{row["id"]}/revisions',headers=h,json=expected(row,content=moved));assert response.status_code==201,response.text
    revised=publish(client,ids,h,response.json());assert revised['content']['state']=='published'
    impacts=client.get(path(ids)+'/session-impacts').json();assert impacts['total']==1
    impact=impacts['items'][0];assert impact['session_revision_id']==planned['revision_id'] and impact['old_revision_id']==row['content']['id']
    login(client,'teacher');assert client.get(path(ids)+'/session-impacts').json()['total']==0
    h=login(client)
    app.state.curriculum_future_session_port.mode='stale'
    payload=expected(impact,decision='keep',reason='Retain adapted activity with prior theme')
    assert client.post(path(ids)+f'/session-impacts/{impact["id"]}/decision',headers=h,json=payload).status_code==409
    app.state.curriculum_future_session_port.mode='current'
    response=client.post(path(ids)+f'/session-impacts/{impact["id"]}/decision',headers=h,json=payload);assert response.status_code==200,response.text
    assert response.json()['state']=='keep'
    after=client.get(base(ids)+f'/teaching/deliveries/{actual_before["id"]}').json()
    assert after['revision_id']==actual_before['revision_id'] and after['activity']==actual_before['activity']
    assert client.get(path(ids)+f'/class-context/{row["content"]["id"]}?on_date=2026-10-21').status_code==409


def test_unavailable_impact_port_atomic_rollback_and_inventory_concurrency(curriculum_env):
    client,factory,app,ids=curriculum_env;h=login(client);row=resource(client,ids,h)
    app.state.curriculum_future_session_port=None
    payload=expected(row,content=resource_content(duration_minutes=20),changes=['Shorter use'])
    response=client.post(path(ids)+f'/resources/{row["id"]}/revisions',headers=h,json=payload)
    assert response.status_code==503,response.text
    with factory() as db:
        assert db.get(m.TeachingResource,row['id']).current_revision==1
        assert db.scalar(select(func.count()).select_from(m.ResourceRevision))==1
        assert db.scalar(select(func.count()).select_from(m.CurriculumEvent))==1
        assert db.scalar(select(func.count()).select_from(m.CommandReceipt))==1
    content={'title':'Synthetic tray','material_type':'tray','location':'Shelf','count':2,'inventory_checked_on':date.today().isoformat(),'presentation_revision_ids':[]}
    response=client.post(path(ids)+'/materials',headers=h,json=retry(content=content));assert response.status_code==201,response.text
    identity=response.json()['id']
    with factory() as left,factory() as right:
        a=left.get(m.MaterialCatalogItem,identity);b=right.get(m.MaterialCatalogItem,identity)
        a.count=3;left.commit();b.count=4
        with pytest.raises(StaleDataError):right.commit()


def test_source_pupil_scope_cannot_be_school_shared_or_bypassed_with_variant(curriculum_env):
    from spesped.contexts.curriculum.adapters import digest
    from spesped.contexts.evidence import service as evidence_service
    from spesped.auth import Actor
    client,factory,app,ids=curriculum_env;h=login(client)
    binding,item=evidence(client,ids,h,learner='b')
    with factory() as db:
        native=evidence_service.evidence(db,Actor(ids['reviewer']),ids['school'],item['id'])
        value=evidence_service.evidence_view(db,native);value['controlled_excerpt']=evidence_service.excerpt_view(db,Actor(ids['reviewer']),ids['school'],value['source']['link_id'])['excerpt']
        ref={'kind':'evidence','source_id':item['id'],'revision':item['revision'],'digest':digest(value),'learner_id':ids['b']}
    row=resource(client,ids,h,sources=[ref])
    response=client.post(path(ids)+f'/resources/{row["id"]}/sharing',headers=h,json=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],visibility='school',reason='Not sufficient for pupil sources'))
    assert response.status_code==403
    variant=client.post(path(ids)+'/resources',headers=h,json=retry(content=resource_content(),original_revision_id=row['revision_id'],changes=['Own adaptation']))
    assert variant.status_code==201,variant.text
    # Even a library manager with read rights has no unassigned pupil access.
    login(client,'teacher');assert client.get(path(ids)+f'/resources/{variant.json()["id"]}').status_code==403
    h=login(client)
    # A correction of the original also invalidates a still-current evidence excerpt.
    original=client.get(base(ids)+f'/intake/{item["source"]["source_id"]}').json()
    from spesped.contexts.evidence.models import SourceItem
    with factory() as db:
        native_source=db.get(SourceItem,original['id'])
        metadata=retry(external_scope=native_source.external_scope,external_id=native_source.external_id,sender='Synthetic source owner',document_type='education_document',received_at=utcnow().isoformat())
    correction=client.post(base(ids)+f'/intake/{original["id"]}/revisions',content=b'Synthetic corrected pupil original',headers={**h,'X-Evidence-Filename':'corrected.txt','X-Evidence-Metadata':json.dumps(metadata),'X-Expected-Version':str(original['version'])})
    assert correction.status_code==201,correction.text
    assert client.get(path(ids)+f'/resources/{row["id"]}').status_code==409
    assert client.get(path(ids)+f'/resources/{variant.json()["id"]}').status_code==409


@pytest.mark.parametrize('partial',[False,True])
def test_resource_experience_uses_real_actual_participation_and_is_not_approval(curriculum_env,partial):
    client,factory,app,ids=curriculum_env;h=login(client);goal,_=ordinary_goal(client,ids,h);row=resource(client,ids,h)
    actual_content=actual(ids,{'a':goal})
    if partial:
        actual_content.update(status='partial',cause='changed_activity',follow_up_owner_id=ids['reviewer'],follow_up='Synthetic review of shortened activity')
        actual_content['participants'][0].update(status='partial',minutes=15)
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual_content));assert response.status_code==201,response.text
    delivery=response.json();observed_on=utcnow().astimezone(__import__('zoneinfo').ZoneInfo('Europe/Oslo')).date()
    from datetime import datetime
    observed_on=datetime.fromisoformat(delivery['occurred_at']).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Oslo')).date()
    payload=retry(resource_revision_id=row['revision_id'],learner_id=ids['a'],session_delivery_revision_id=delivery['revision_id'],observed_on=observed_on.isoformat(),experience='Synthetic actual use: the large-print labels were useful')
    response=client.post(path(ids)+'/resource-experiences',headers=h,json=payload);assert response.status_code==201,response.text
    assert response.json()['constitutes_approval'] is False
    assert client.get(path(ids)+f'/resource-experiences?learner_id={ids["a"]}').json()['total']==1
    payload.update(request_key=key(),learner_id=ids['b'])
    assert client.post(path(ids)+'/resource-experiences',headers=h,json=payload).status_code==403


def test_license_derivatives_cannot_expand_rights_and_recall_is_deduplicated(curriculum_env):
    from spesped.auth import Actor
    from spesped.contexts.curriculum import service as curriculum
    client,factory,app,ids=curriculum_env;h=login(client);ref,_=source(client,ids,h)
    original=resource(client,ids,h,sources=[ref])
    expanded=resource_content();expanded['rights']['ai']=True
    response=client.post(path(ids)+'/resources',headers=h,json=retry(content=expanded,original_revision_id=original['revision_id'],changes=['Synthetic variant']))
    assert response.status_code==403,response.text
    goal,_=ordinary_goal(client,ids,h);planned=session(client,ids,h,basis(client,ids,h,{'a':goal}))
    app.state.curriculum_future_session_port.dependencies[original['revision_id']]=[planned['revision_id']]
    with factory() as db:
        db.info['curriculum_future_session_port']=app.state.curriculum_future_session_port
        result=curriculum.record_source_correction_impacts(db,Actor(ids['reviewer']),ids['school'],ref);db.commit()
        assert result['affected_revisions']==1
        result=curriculum.record_source_correction_impacts(db,Actor(ids['reviewer']),ids['school'],ref);db.commit()
        assert result['affected_revisions']==1
        assert db.scalar(select(func.count()).select_from(m.SessionImpact))==1
        assert db.scalar(select(func.count()).select_from(m.CurriculumEvent).where(m.CurriculumEvent.event_type=='curriculum.source.review_required'))==1
    impacts=client.get(path(ids)+'/session-impacts').json();assert impacts['total']==1


def test_withdrawal_reauthorization_and_scheme_draft_does_not_change_published_context(curriculum_env):
    client,factory,app,ids=curriculum_env;h=login(client);sc,content=scheme(client,ids,h)
    plan=publish(client,ids,h,class_plan(client,ids,h,plan_content(sc)))
    response=client.post(path(ids)+f'/schemes/{sc["id"]}/revisions',headers=h,json=expected(sc,content={**content,'title':'Synthetic pending curriculum correction'}))
    assert response.status_code==201,response.text
    revised=response.json()
    assert client.get(path(ids)+f'/class-context/{plan["content"]["id"]}?on_date=2026-10-21').status_code==200
    response=client.post(path(ids)+f'/schemes/{sc["id"]}/review',headers=h,json=expected(revised,revision_id=revised['content']['id'],content_digest=revised['content']['content_digest'],reason='Synthetic reviewed correction',approval_reference='Synthetic new school approval',approved_on=date.today().isoformat()))
    assert response.status_code==200,response.text
    assert client.get(path(ids)+f'/class-context/{plan["content"]["id"]}?on_date=2026-10-21').status_code==409
    response=client.post(path(ids)+f'/class-plans/{plan["id"]}/withdraw',headers=h,json=expected(plan,reason='Synthetic source correction'))
    assert response.status_code==200,response.text
    row=resource(client,ids,h);payload=expected(row,reason='Synthetic withdrawal of further uses')
    response=client.post(path(ids)+f'/resources/{row["id"]}/withdraw',headers=h,json=payload);assert response.status_code==200,response.text
    assert client.post(path(ids)+f'/resources/{row["id"]}/withdraw',headers=h,json=payload).json()==response.json()
    assert client.get(path(ids)+f'/resource-revisions/{row["revision_id"]}?purpose=use').status_code==409


def test_postgres_concurrent_same_logical_command_one_outbox(curriculum_env):
    from concurrent.futures import ThreadPoolExecutor
    from spesped.auth import Actor
    from spesped.contexts.curriculum import service as svc,schemas as s
    client,factory,app,ids=curriculum_env
    if factory.kw['bind'].dialect.name!='postgresql':pytest.skip('Real PostgreSQL locking verification')
    command=s.ResourceCreate(**retry(content=resource_content()))
    def invoke():
        with factory() as db:return svc.create_resource(db,Actor(ids['reviewer']),ids['school'],command)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(invoke) for _ in range(2)];results=[f.result(timeout=10) for f in futures]
    assert results[0]==results[1]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.TeachingResource))==1
        assert db.scalar(select(func.count()).select_from(m.CommandReceipt))==1
        assert db.scalar(select(func.count()).select_from(m.CurriculumEvent))==1


@pytest.mark.parametrize('dialect',['sqlite','postgres'])
def test_owned_migration_roundtrip_schema_and_data_loss_refusal(tmp_path,dialect):
    import os
    from sqlalchemy.engine import make_url
    from sqlalchemy import inspect
    from alembic.migration import MigrationContext
    from alembic.autogenerate import compare_metadata
    from spesped.db import Base,make_session_factory
    from spesped.cli import provision_school
    schema=None;admin=None
    if dialect=='postgres':
        url=os.environ.get('SPESPED_TEST_POSTGRES_URL')
        if not url:pytest.skip('PostgreSQL test URL not configured')
        assert make_url(url).database!='spesped_demo'
        schema='j09_migration_'+uuid4().hex;admin=create_engine(url)
        with admin.begin() as connection:connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else:url=f'sqlite:///{tmp_path}/curriculum-roundtrip.db'
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=url
    engine=create_engine(url);factory=make_session_factory(url)
    try:
        command.upgrade(config,'j09_curriculum')
        with engine.connect() as connection:
            current=MigrationContext.configure(connection,opts={'include_object':lambda obj,name,type_,reflected,compare_to: name.startswith('curriculum_') if type_=='table' else True})
            differences=compare_metadata(current,Base.metadata)
            assert not differences,differences
        command.downgrade(config,'b5_generated_teaching')
        assert not any(n.startswith('curriculum_') for n in inspect(engine).get_table_names())
        command.upgrade(config,'j09_curriculum')
        with factory.begin() as db:
            school,leader=provision_school(db,school_name='Synthetic migration school',kind='public',timezone='Europe/Oslo',email='migration@example.invalid',display_name='Synthetic leader',password='synthetic-migration-passphrase')
            db.add(m.ResourceTeam(school_id=school.id,name='Synthetic retained team',state='active'))
        with pytest.raises(RuntimeError,match='Refusing to discard'):
            command.downgrade(config,'b5_generated_teaching')
        assert 'curriculum_resource_teams' in inspect(engine).get_table_names()
        with factory() as db:assert db.scalar(select(func.count()).select_from(m.ResourceTeam))==1
    finally:
        factory.kw['bind'].dispose();engine.dispose()
        if schema:
            with admin.begin() as connection:connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def test_consumer_read_ports_preserve_pending_changes_and_fail_closed(curriculum_env):
    from spesped.auth import Actor
    from spesped.contexts.curriculum.service import resolve_resource
    from spesped.errors import DomainError
    client,factory,app,ids=curriculum_env;h=login(client);row=resource(client,ids,h)
    with factory() as db:
        original=db.get(m.ResourceRevision,row['revision_id'])
        original.title='Synthetic unflushed correction'
        with pytest.raises(DomainError,match='pending'):
            resolve_resource(db,Actor(ids['reviewer']),ids['school'],original.id)
        assert original.title=='Synthetic unflushed correction' and original in db.dirty
        db.rollback()
        assert resolve_resource(db,Actor(ids['reviewer']),ids['school'],original.id)['title']==row['title']


def test_binding_correction_one_current_choice_retains_history_and_retries(curriculum_env):
    from curriculum_fixtures import bound_theme,correction
    client,factory,app,ids=curriculum_env;h=login(client)
    first,creation,plan=bound_theme(client,ids,h)
    assert first['is_current'] and first['supersedes_id'] is None
    # A new key for a conflicting fresh create is not a correction command.
    duplicate={**creation,'request_key':key(),'participation':'not_relevant','adaptation':None,'materials':[]}
    assert client.post(path(ids)+'/theme-goal-bindings',headers=h,json=duplicate).status_code==409
    payload=correction(first,creation['sources'])
    target=path(ids)+f'/theme-goal-bindings/{first["id"]}/corrections'
    response=client.post(target,headers=h,json=payload);assert response.status_code==201,response.text
    changed=response.json()
    assert changed['participation']=='not_relevant' and changed['is_current']
    assert changed['supersedes_id']==first['id'] and changed['correction_reason']==payload['reason']
    assert client.post(target,headers=h,json=payload).json()==changed
    assert client.post(target,headers=h,json={**payload,'request_key':key()}).status_code==409
    assert client.post(target,headers=h,json={**payload,'reason':'Conflicting key reuse'}).status_code==409
    context=client.get(path(ids)+f'/class-context/{plan["content"]["id"]}?on_date=2026-10-21&learner_id={ids["a"]}')
    assert context.status_code==200,context.text
    assert [b['participation'] for b in context.json()['bindings']]==['not_relevant']
    history=client.get(path(ids)+f'/theme-goal-bindings?learner_id={ids["a"]}').json()['items']
    assert len(history)==2
    old=next(row for row in history if row['id']==first['id'])
    assert old['state']=='superseded' and not old['is_current'] and old['superseded_by_id']==changed['id']
    assert old['adaptation']==creation['adaptation'] and old['bound_by']==ids['reviewer']
    # A replay acknowledges the original command while exposing its current historical state.
    replay=client.post(path(ids)+'/theme-goal-bindings',headers=h,json=creation)
    assert replay.status_code==201 and replay.json()['state']=='superseded' and not replay.json()['is_current']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.ThemeGoalBinding).where(m.ThemeGoalBinding.state=='active'))==1
        assert db.scalar(select(func.count()).select_from(m.CurriculumEvent).where(m.CurriculumEvent.event_type=='curriculum.theme.goal_binding_corrected'))==1


def test_binding_database_uniqueness_distinct_goals_and_learner_scope(curriculum_env):
    from curriculum_fixtures import bound_theme,correction
    from plans_fixtures import plan_payload,activate
    from sqlalchemy.exc import IntegrityError
    client,factory,app,ids=curriculum_env;h=login(client)
    payload=plan_payload();payload['goals'].append({**payload['goals'][0],'title':'Synthetic distinct second goal','expected_action':'Recognise a continent label'})
    response=client.post(base(ids)+f'/learners/{ids["a"]}/education-plans',headers=h,json=payload)
    assert response.status_code==201,response.text
    active=activate(client,ids,h,response.json());goal_ids=[g['id'] for g in active['content']['goals']]
    reviewed,_=scheme(client,ids,h);content=plan_content(reviewed);plan=publish(client,ids,h,class_plan(client,ids,h,content));ref,_=source(client,ids,h)
    bindings=[]
    for goal_id in goal_ids:
        payload=retry(plan_revision_id=plan['content']['id'],theme_id=content['themes'][0]['id'],learner_id=ids['a'],goal_revision_id=goal_id,participation='participate',rationale='Synthetic separate pupil goal',sources=[ref])
        response=client.post(path(ids)+'/theme-goal-bindings',headers=h,json=payload);assert response.status_code==201,response.text
        bindings.append(response.json())
    assert len(client.get(path(ids)+f'/class-context/{plan["content"]["id"]}?on_date=2026-10-21&learner_id={ids["a"]}').json()['bindings'])==2
    with factory() as db:
        original=db.get(m.ThemeGoalBinding,bindings[0]['id'])
        values={column.name:getattr(original,column.name) for column in original.__table__.columns if column.name not in {'id','created_at','updated_at','version'}}
        db.add(m.ThemeGoalBinding(**values))
        with pytest.raises(IntegrityError):db.commit()
    # A manager without this pupil's assignment cannot probe a stale version or correct it.
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids['teacher'],StaffAssignment.learner_id==ids['a'])):assignment.state='revoked'
    h=login(client,'teacher')
    command_payload=correction(bindings[0],[ref]);command_payload['expected_version']=999
    assert client.post(path(ids)+f'/theme-goal-bindings/{bindings[0]["id"]}/corrections',headers=h,json=command_payload).status_code==403
    assert client.post(path(ids)+f'/theme-goal-bindings/{uuid4()}/corrections',headers=h,json=command_payload).status_code==403


def test_postgres_concurrent_corrections_one_current_choice(curriculum_env):
    from concurrent.futures import ThreadPoolExecutor
    from curriculum_fixtures import bound_theme,correction
    from spesped.contexts.curriculum import service as svc,schemas as s
    from spesped.auth import Actor
    from spesped.errors import DomainError
    client,factory,app,ids=curriculum_env
    if factory.kw['bind'].dialect.name!='postgresql':pytest.skip('Real PostgreSQL competing correction locking')
    h=login(client);first,creation,_=bound_theme(client,ids,h)
    commands=[s.GoalBindingCorrection(**correction(first,creation['sources'])) for _ in range(2)]
    def invoke(command):
        with factory() as db:
            from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
            db.info['curriculum_source_port']=EvidenceSourceReadPort(app.state.evidence_storage)
            try:return svc.correct_goal_binding(db,Actor(ids['reviewer']),ids['school'],first['id'],command)
            except DomainError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(invoke,cmd) for cmd in commands];results=[future.result(timeout=15) for future in futures]
    assert len([r for r in results if isinstance(r,dict)])==1 and 'version_conflict' in results
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.ThemeGoalBinding))==2
        assert db.scalar(select(func.count()).select_from(m.ThemeGoalBinding).where(m.ThemeGoalBinding.state=='active'))==1
        assert db.get(m.ThemeGoalBinding,first['id']).version==2


def test_experience_currentness_after_actual_correction_and_idempotent_replay(curriculum_env):
    from curriculum_fixtures import resource_experience
    from spesped.auth import Actor
    from spesped.contexts.curriculum import service as svc
    from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
    client,factory,app,ids=curriculum_env;h=login(client)
    saved,payload,delivery,actual_content,res=resource_experience(client,ids,h)
    assert saved['state']=='current' and saved['actual_status']=='current' and not saved['review_required']
    with factory() as cached:
        cached.info['curriculum_source_port']=EvidenceSourceReadPort(app.state.evidence_storage)
        row=cached.get(m.ResourceExperience,saved['id'])
        assert svc.experience_view(cached,Actor(ids['reviewer']),row)['state']=='current'
        from spesped.contexts.teaching.models import SessionDelivery
        retained_actual=cached.get(SessionDelivery,delivery['id'])
        assert retained_actual.current_revision==1
        actual_content['participants'][0].update(status='absent',minutes=0)
        actual_content.update(status='partial',cause='learner_absence',follow_up_owner_id=ids['reviewer'],follow_up='Synthetic review after corrected absence')
        response=client.post(base(ids)+f'/teaching/deliveries/{delivery["id"]}/corrections',headers=h,json=expected(delivery,content=actual_content,reason='Synthetic correction of participation'))
        assert response.status_code==200,response.text
        assert retained_actual.current_revision==1
        value=svc.experience_view(cached,Actor(ids['reviewer']),row)
        assert retained_actual.current_revision==2
        assert value['state']=='review_required' and value['actual_status']=='historical'
        assert value['session_delivery_revision_id']==delivery['revision_id'] and value['experience']==saved['experience']
        assert value['review_required'] and value['constitutes_approval'] is False
    listed=client.get(path(ids)+f'/resource-experiences?learner_id={ids["a"]}').json()['items'][0]
    assert listed['actual_status']=='historical' and listed['source_status']=='review_required'
    assert client.post(path(ids)+'/resource-experiences',headers=h,json={**payload,'request_key':key()}).status_code==409
    replay=client.post(path(ids)+'/resource-experiences',headers=h,json=payload)
    assert replay.status_code==201 and replay.json()['actual_status']=='historical'
    with factory() as db:
        retained=db.get(m.ResourceExperience,saved['id'])
        assert retained.experience==saved['experience'] and retained.session_delivery_revision_id==delivery['revision_id']


def test_experience_current_source_and_revoked_cached_rights_redact_prose(curriculum_env):
    from curriculum_fixtures import resource_experience
    from spesped.auth import Actor
    from spesped.contexts.curriculum import service as svc
    from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
    from spesped.errors import DomainError
    client,factory,app,ids=curriculum_env;h=login(client);ref,_=source(client,ids,h)
    saved,payload,delivery,actual_content,res=resource_experience(client,ids,h,sources=[ref])
    with factory() as cached:
        cached.info['curriculum_source_port']=EvidenceSourceReadPort(app.state.evidence_storage)
        row=cached.get(m.ResourceExperience,saved['id'])
        assert svc.experience_view(cached,Actor(ids['reviewer']),row)['content_available']
        retained_grant=cached.scalar(select(AuthorityGrant).where(AuthorityGrant.school_id==ids['school'],AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='curriculum.source.read'))
        retained_assignment=cached.scalar(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a']))
        with factory.begin() as db:
            grant=db.scalar(select(AuthorityGrant).where(AuthorityGrant.school_id==ids['school'],AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='curriculum.source.read'));grant.state='revoked'
        assert retained_grant.state=='active'
        value=svc.experience_view(cached,Actor(ids['reviewer']),row)
        assert value['resource_status']=='unavailable' and value['experience'] is None and value['review_required']
        assert value['session_delivery_revision_id']==delivery['revision_id'] and value['actual_status']=='current'
        listed=client.get(path(ids)+f'/resource-experiences?learner_id={ids["a"]}').json()['items'][0]
        assert listed['experience'] is None and not listed['content_available']
        replay=client.post(path(ids)+'/resource-experiences',headers=h,json=payload)
        assert replay.status_code==201 and replay.json()['experience'] is None
        with factory.begin() as db:
            for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a'])):assignment.state='revoked'
        assert retained_assignment.state=='active'
        with pytest.raises(DomainError) as denied:svc.experience_view(cached,Actor(ids['reviewer']),row)
        assert denied.value.status_code==403
    assert client.get(path(ids)+f'/resource-experiences?learner_id={ids["a"]}').status_code==403
    assert client.post(path(ids)+'/resource-experiences',headers=h,json=payload).status_code==403


def test_experience_original_replacement_and_resource_withdrawal_mark_history(curriculum_env):
    from curriculum_fixtures import resource_experience
    from spesped.contexts.evidence.models import SourceItem
    client,factory,app,ids=curriculum_env;h=login(client);ref,original=source(client,ids,h)
    saved,payload,delivery,actual_content,res=resource_experience(client,ids,h,sources=[ref])
    with factory() as db:
        item=db.get(SourceItem,original['id'])
        metadata=retry(external_scope=item.external_scope,external_id=item.external_id,sender='Synthetic original owner',document_type='curriculum',received_at=utcnow().isoformat())
    response=client.post(base(ids)+f'/intake/{original["id"]}/revisions',content=b'Synthetic corrected resource source',headers={**h,'X-Evidence-Filename':'corrected.txt','X-Evidence-Metadata':json.dumps(metadata),'X-Expected-Version':str(original['version'])})
    assert response.status_code==201,response.text
    listed=client.get(path(ids)+f'/resource-experiences?learner_id={ids["a"]}&resource_revision_id={res["revision_id"]}').json()['items'][0]
    assert listed['id']==saved['id'] and listed['resource_revision_id']==res['revision_id']
    assert listed['state']=='review_required' and listed['actual_status']=='current' and listed['resource_status']=='unavailable'
    assert listed['experience'] is None and not listed['content_available']
    # Withdrawal independently removes current resource support while retaining the account.
    second_res=resource(client,ids,h)
    response=client.post(path(ids)+'/resource-experiences',headers=h,json={**payload,'request_key':key(),'resource_revision_id':second_res['revision_id']})
    assert response.status_code==201,response.text
    second=response.json()
    response=client.post(path(ids)+f'/resources/{second_res["id"]}/withdraw',headers=h,json=expected(second_res,reason='Synthetic withdrawal of the presentation'))
    assert response.status_code==200,response.text
    listed=client.get(path(ids)+f'/resource-experiences?learner_id={ids["a"]}&resource_revision_id={second_res["revision_id"]}').json()['items'][0]
    assert listed['id']==second['id'] and listed['resource_status']=='unavailable' and listed['review_required']
    assert listed['experience'] is None and listed['actual_status']=='current'
    with factory() as db:
        assert db.get(m.ResourceExperience,saved['id']).experience==saved['experience']
        assert db.get(m.ResourceExperience,second['id']).experience==second['experience']
