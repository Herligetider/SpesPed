from datetime import timedelta,date
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from assessment_fixtures import *
from spesped.contexts.assessment import models as m
from spesped.db import utcnow

def test_exact_instrument_scales_lifecycle_corrections_and_followup(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);ins,content=instrument(client,ids,h)
    plan=planned(client,ids,h,ins);row=started(client,ids,h,plan)
    bad=expected(row,occurred_at=(utcnow()-timedelta(hours=1)).isoformat(),raw={'raw':'21'},conditions=conditions())
    response=client.post(path(ids)+f'/administrations/{row["id"]}/results',headers=h,json=bad);assert response.status_code==422,response.text
    assert client.get(path(ids)+f'/administrations/{row["id"]}').json()['state']=='started'
    row=recorded(client,ids,h,row);old=row['result'];row=reviewed(client,ids,h,row)
    follow=client.get(path(ids)+f'/learners/{ids["a"]}/follow-ups').json()['items'][0]
    assert follow['proposed_on']==(date.today()+timedelta(days=30)).isoformat()
    response=client.post(path(ids)+f'/follow-ups/{follow["id"]}/decision',headers=h,json=expected(follow,decision='moved',selected_on=(date.today()+timedelta(days=10)).isoformat(),reason='Too soon'))
    assert response.status_code==409
    response=client.post(path(ids)+f'/follow-ups/{follow["id"]}/decision',headers=h,json=expected(follow,decision='moved',selected_on=(date.today()+timedelta(days=45)).isoformat(),reason='Synthetic eligible later appointment'))
    assert response.status_code==200,response.text
    row=recorded(client,ids,h,row,correction_reason='Synthetic transcription correction')
    assert row['state']=='recorded' and row['result']['id']!=old['id'] and row['interpretation'] is None
    history=client.get(path(ids)+f'/administrations/{row["id"]}/results').json()['items']
    assert len(history)==2 and history[0]['digest']==old['digest']
    with factory() as db:
        db.get(m.ResultRevision,old['id']).raw={'raw':'9'}
        with pytest.raises(ValueError):db.commit()

def test_unknown_authority_does_not_become_qualification_and_unbased_interval_stays_open(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);ins,_=instrument(client,ids,h,guidance=False)
    app.state.assessment_authority_port=None
    row=planned(client,ids,h,ins);assert row['qualification_status']=='unavailable'
    response=client.post(path(ids)+f'/administrations/{row["id"]}/start',headers=h,json=expected(row,occurred_at=(utcnow()-timedelta(hours=2)).isoformat()));assert response.status_code==409
    app.state.assessment_authority_port=SyntheticAssessmentAuthority();row=reviewed(client,ids,h,recorded(client,ids,h,started(client,ids,h,row)))
    follow=client.get(path(ids)+f'/learners/{ids["a"]}/follow-ups').json()['items'][0]
    assert follow['state']=='open_professional_question' and follow['proposed_on'] is None
    response=client.post(path(ids)+f'/follow-ups/{follow["id"]}/decision',headers=h,json=expected(follow,decision='accepted',selected_on=(date.today()+timedelta(days=30)).isoformat(),reason='Caller invented interval'));assert response.status_code==409
    response=client.post(path(ids)+f'/follow-ups/{follow["id"]}/decision',headers=h,json=expected(follow,decision='rejected',reason='No source supports an interval'));assert response.status_code==200,response.text

def test_idempotency_rechecks_live_scope_and_conflicting_payload(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);ins,_=instrument(client,ids,h)
    payload=retry(learner_id=ids['a'],instrument_revision_id=ins['revision_id'],planned_on=date.today().isoformat(),purpose='Synthetic exact retry',conditions=conditions())
    url=path(ids)+'/administrations';r=client.post(url,headers=h,json=payload);assert r.status_code==201,r.text
    repeat=client.post(url,headers=h,json=payload);assert repeat.json()['id']==r.json()['id']
    changed={**payload,'purpose':'Different semantic command'};assert client.post(url,headers=h,json=changed).status_code==409
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a'])):assignment.state='revoked'
    assert client.get(path(ids)+f'/administrations/{r.json()["id"]}').status_code==403
    assert client.post(url,headers=h,json=payload).status_code==403

def test_wrong_authority_scope_rollback_and_cross_pupil_source(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);ins,_=instrument(client,ids,h);row=planned(client,ids,h,ins)
    with factory() as db:before=db.scalar(select(func.count()).select_from(m.AssessmentEvent))
    app.state.assessment_authority_port.wrong=True
    response=client.post(path(ids)+f'/administrations/{row["id"]}/start',headers=h,json=expected(row,occurred_at=(utcnow()-timedelta(hours=2)).isoformat()));assert response.status_code==409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.AssessmentEvent))==before
        assert db.get(m.Administration,row['id']).state=='planned'
    payload=retry(learner_id=str(uuid4()),instrument_revision_id=ins['revision_id'],planned_on=date.today().isoformat(),purpose='Wrong pupil',conditions=conditions())
    assert client.post(path(ids)+'/administrations',headers=h,json=payload).status_code==403

def test_comparison_versions_and_aborted_are_visible(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);ins,content=instrument(client,ids,h)
    arow=recorded(client,ids,h,started(client,ids,h,planned(client,ids,h,ins)))
    other=planned(client,ids,h,ins)
    response=client.post(path(ids)+f'/administrations/{other["id"]}/abort',headers=h,json=expected(other,reason='Synthetic interrupted attempt'));assert response.status_code==200,response.text
    assert response.json()['state']=='aborted' and response.json()['result'] is None
    content['publisher_version']='synthetic-2'
    response=client.post(path(ids)+f'/instruments/{ins["id"]}/revisions',headers=h,json=expected(ins,content=content));assert response.status_code==201,response.text
    old=client.get(path(ids)+f'/administrations/{arow["id"]}').json();assert old['source_status']=='review_required'
    assert old['result']['id']==arow['result']['id'] and old['universal_score'] is None

def exact_progress(row,**changes):return expected(row,revision_id=row['content']['id'],content_digest=row['content']['digest'],reason='Synthetic exact human review',**changes)

def test_progress_actuals_observations_immutable_confirmation_and_late_evidence(assessment_env):
    from teaching_fixtures import actual
    client,factory,app,ids=assessment_env;h=login(client);goal_id,_=ordinary_goal(client,ids,h)
    observed=observation(client,ids,h,goal_id)
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual(ids,{'a':goal_id})));assert response.status_code==201,response.text
    delivery=response.json()
    row=progress(client,ids,h,goal_id,delivery_revision_ids=[delivery['revision_id']])
    assert row['snapshot']['observations'][0]['revision_id']==observed['revision_id']
    assert row['snapshot']['actual_deliveries'][0]['delivery_revision_id']==delivery['revision_id']
    assert row['snapshot']['planned_activity_is_evidence'] is False
    assert row['snapshot']['observations'][0]['occurred_at']!=row['snapshot']['observations'][0]['created_at']
    for transition in ('submit','confirm'):
        response=client.post(path(ids)+f'/progress-reviews/{row["id"]}/review',headers=h,json=exact_progress(row,transition=transition));assert response.status_code==200,response.text
        row=response.json()
    final_id=row['content']['id'];snapshot_digest=row['snapshot_digest']
    assert row['state']=='confirmed'
    response=client.post(path(ids)+f'/progress-reviews/{row["id"]}/revisions',headers=h,json=expected(row,finding=finding(outcome='adapt')));assert response.status_code==409
    # A late-entered observation occurred inside the frozen historical interval.
    late=observation(client,ids,h,goal_id,occurred_at=observed['occurred_at'],observation='Synthetic later-entered contradictory attempt',support='Synthetic additional support')
    current=client.get(path(ids)+f'/progress-reviews/{row["id"]}').json()
    assert current['review_required'] and late['revision_id'] in current['late_evidence_revision_ids']
    assert current['content']['id']==final_id and current['snapshot_digest']==snapshot_digest
    assert current['snapshot']['universal_pupil_score'] is None

def test_missing_learning_evidence_is_gap_and_changed_support_is_visible(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);goal_id,_=ordinary_goal(client,ids,h)
    payload=retry(learner_id=ids['a'],goal_revision_id=goal_id,starts_at=(utcnow()-timedelta(days=1)).isoformat(),ends_at=utcnow().isoformat(),finding=finding())
    response=client.post(path(ids)+'/progress-reviews',headers=h,json=payload);assert response.status_code==409,response.text
    payload['request_key']=key();payload['finding']=finding(outcome='more_information',missing_evidence=['Need actual observations'])
    response=client.post(path(ids)+'/progress-reviews',headers=h,json=payload);assert response.status_code==201,response.text
    assert 'insufficient_documented_learning_evidence' in response.json()['snapshot']['gaps']
    observation(client,ids,h,goal_id);observation(client,ids,h,goal_id,support='Synthetic support changed')
    row=progress(client,ids,h,goal_id,finding=finding(comparison_limitations=['Support varied; no independent mastery inferred']))
    assert 'varied_recorded_support' in row['snapshot']['comparison_limitations']

def test_progress_current_reads_and_replay_redact_revoked_original_source(assessment_env):
    from spesped.contexts.evidence.models import SourceSubjectLink
    client,factory,app,ids=assessment_env;h=login(client);binding,item=evidence(client,ids,h)
    goal_id,_=ordinary_goal(client,ids,h,binding=binding)
    observed=observation(client,ids,h,goal_id)
    payload=retry(learner_id=ids['a'],goal_revision_id=goal_id,starts_at=(utcnow()-timedelta(days=1)).isoformat(),ends_at=utcnow().isoformat(),finding=finding())
    response=client.post(path(ids)+'/progress-reviews',headers=h,json=payload);assert response.status_code==201,response.text
    row=response.json()
    with factory.begin() as db:db.get(SourceSubjectLink,binding['link_id']).revoked_at=utcnow()
    current=client.get(path(ids)+f'/progress-reviews/{row["id"]}').json()
    assert current['snapshot'] is None and current['content'] is None and current['source_status']=='unavailable'
    replay=client.post(path(ids)+'/progress-reviews',headers=h,json=payload);assert replay.status_code==201,replay.text
    assert replay.json()['snapshot'] is None and replay.json()['content'] is None

def evidence_reference(binding):return {'kind':'evidence','id':binding['evidence_id'],'revision':binding['evidence_revision'],'link_id':binding['link_id']}
def competence(binding,**changes):return {'reference':evidence_reference(binding),'curriculum_goal_code':'READ1','role':'subject_competence','relevance':'Synthetic human selected subject competence evidence',**changes}

def test_statement_scheme_difference_contributions_human_grade_and_communication(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);sc,_=scheme(client,ids,h);mont,_=scheme(client,ids,h,pedagogy='montessori')
    binding,item=evidence(client,ids,h)
    content=statement_content(basis=[competence(binding)],expected_contributors=[ids['reviewer']])
    row=statement(client,ids,h,sc,content=content)
    other=statement(client,ids,h,mont,content=content)
    assert row['scheme']['pedagogy']=='public' and other['scheme']['pedagogy']=='montessori'
    assert other['scheme']['assessment_rules'][0]['exception_basis']
    assert row['missing_contributor_ids']==[ids['reviewer']]
    response=client.post(path(ids)+f'/statements/{row["id"]}/contributions',headers=h,json=expected(row,kind='staff',occurred_at=(utcnow()-timedelta(hours=1)).isoformat(),content='Synthetic staff account tied to selected evidence',sources=[evidence_reference(binding)]));assert response.status_code==201,response.text
    row=response.json();assert row['missing_contributor_ids']==[]
    payload=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic exact subject statement and contributions approved',contribution_ids=[c['id'] for c in row['contributions']],grade='B')
    response=client.post(path(ids)+f'/statements/{row["id"]}/finalize',headers=h,json=payload);assert response.status_code==200,response.text
    row=response.json();assert row['finalization']['grade']=='B' and row['finalization']['authorized_person_id']==ids['reviewer']
    assert row['finalization']['grade_authority']['request']['purpose']=='grade_set' and row['finalization']['authority_binding']['request']['purpose']=='statement_finalize'
    assert row['communications']==[] and row['external_send_performed'] is False
    for destination in ('pupil','guardian','authoritative_system'):
        response=client.post(path(ids)+f'/statements/{row["id"]}/communications',headers=h,json=expected(row,revision_id=row['revision_id'],occurred_at=(utcnow()-timedelta(minutes=1)).isoformat(),destination=destination,method='Synthetic manual record',factual_reference='Synthetic dated factual communication log'))
        assert response.status_code==201,response.text;row=response.json()
    assert {c['destination'] for c in row['communications']}=={'pupil','guardian','authoritative_system'}
    assert row['external_send_performed'] is False
    # A different actor cannot inherit finalization on a replayed request key.
    teacher_headers=login(client,'teacher')
    replay=client.post(path(ids)+f'/statements/{row["id"]}/finalize',headers=teacher_headers,json=payload);assert replay.status_code==409

def test_unresolved_scheme_exemptions_completion_and_authority_remain_explicit(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client)
    unresolved=statement(client,ids,h,None);assert unresolved['state']=='needs_basis' and 'assessment_scheme_unresolved' in unresolved['unresolved']
    sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h)
    row=statement(client,ids,h,sc,assessment_type='final',content=statement_content(basis=[competence(binding)],completion='completes_in_period'))
    payload=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic final review',contribution_ids=[])
    response=client.post(path(ids)+f'/statements/{row["id"]}/finalize',headers=h,json=payload);assert response.status_code==409
    app.state.assessment_authority_port.completion='completes_in_period';app.state.assessment_authority_port=None
    response=client.post(path(ids)+f'/statements/{row["id"]}/finalize',headers=h,json=payload);assert response.status_code==409 and response.json()['error']['code']=='assessment_authority_unresolved'
    assert client.get(path(ids)+f'/statements/{row["id"]}').json()['state']!='finalized'
    app.state.assessment_authority_port=SyntheticAssessmentAuthority();app.state.assessment_authority_port.completion='completes_in_period'
    app.state.assessment_authority_port.exemption='assessment_exempt'
    response=client.post(path(ids)+f'/statements/{row["id"]}/finalize',headers=h,json=payload);assert response.status_code==409

def test_iop_progress_cannot_become_subject_grade_basis(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);goal_id,_=ordinary_goal(client,ids,h);observation(client,ids,h,goal_id)
    progress_row=progress(client,ids,h,goal_id)
    for transition in ('submit','confirm'):
        response=client.post(path(ids)+f'/progress-reviews/{progress_row["id"]}/review',headers=h,json=exact_progress(progress_row,transition=transition));assert response.status_code==200,response.text;progress_row=response.json()
    sc,_=scheme(client,ids,h)
    ref={'kind':'progress_review','id':progress_row['id'],'revision':progress_row['content']['number']}
    basis={'reference':ref,'curriculum_goal_code':'READ1','role':'subject_competence','relevance':'Caller attempts silent IOP conversion'}
    response=client.post(path(ids)+'/statements',headers=h,json=retry(learner_id=ids['a'],scheme_revision_id=sc['content']['id'],subject='reading',assessment_type='half_year',starts_on='2026-10-01',ends_on='2026-10-21',content=statement_content(basis=[basis])))
    assert response.status_code==409,response.text
    basis['role']='iop_context';row=statement(client,ids,h,sc,content=statement_content(basis=[basis]))
    assert row['state']=='needs_basis' and 'subject_competence_basis_missing' in row['unresolved']

def test_recorded_learner_self_assessment_uses_own_attributed_source(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);sc,_=scheme(client,ids,h)
    response=client.post(base(ids)+'/intake/notes',headers=h,json=retry(external_scope='manual',external_id=key(),sender='Synthetic staff recorder',document_type='learner_account',received_at=utcnow().isoformat(),text='Synthetic learner account: I want to practise short words'))
    assert response.status_code==201,response.text
    proposal=client.get(base(ids)+f'/intake/{response.json()["id"]}/proposals').json()['items'][0]
    reviewed_source=client.post(base(ids)+f'/extraction-proposals/{proposal["id"]}/review',headers=h,json={'expected_version':proposal['version'],'outcome':'accepted','reason':'Synthetic learner account checked'})
    response=client.post(base(ids)+f'/extraction-proposals/{proposal["id"]}/confirm',headers=h,json={'expected_version':reviewed_source.json()['version'],'learner_id':ids['a'],'claim_type':'report','reporter':'Synthetic pupil own account recorded by staff','source_type':'reported_information','certainty':'confirmed','occurred_at':(utcnow()-timedelta(days=1)).isoformat(),'topic':'self_assessment','excerpt_page':proposal['page'],'excerpt_start':proposal['span_start'],'excerpt_end':proposal['span_end']})
    assert response.status_code==201,response.text;item=response.json()
    ref={'kind':'evidence','id':item['id'],'revision':item['revision'],'link_id':item['source']['link_id']}
    row=statement(client,ids,h,sc)
    payload=expected(row,kind='learner_self_assessment',occurred_at=(utcnow()-timedelta(hours=1)).isoformat(),content='Synthetic recorded learner own account',sources=[ref])
    assert client.post(path(ids)+f'/statements/{row["id"]}/contributions',headers=h,json=payload).status_code==422
    payload['learner_account_confirmed']=True
    response=client.post(path(ids)+f'/statements/{row["id"]}/contributions',headers=h,json=payload);assert response.status_code==201,response.text
    contribution=response.json()['contributions'][0]
    assert contribution['kind']=='learner_self_assessment' and contribution['author_id']==ids['reviewer'] and contribution['sources'][0]['id']==item['id']

def test_missing_scheme_recovery_and_recalled_grade_authority(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);row=statement(client,ids,h,None)
    sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h)
    response=client.post(path(ids)+f'/statements/{row["id"]}/revisions',headers=h,json=expected(row,scheme_revision_id=sc['content']['id'],content=statement_content(basis=[competence(binding)])))
    assert response.status_code==201,response.text;row=response.json()
    assert row['state']=='under_work' and row['scheme']['scheme_revision_id']==sc['content']['id']
    payload=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic subject teacher manual grade',contribution_ids=[],grade='B')
    response=client.post(path(ids)+f'/statements/{row["id"]}/finalize',headers=h,json=payload);assert response.status_code==200,response.text
    row=response.json();app.state.assessment_authority_port.state='unresolved'
    current=client.get(path(ids)+f'/statements/{row["id"]}').json()
    assert current['state']=='finalized' and current['source_status']=='review_required' and current['finalization_authority_status']=='unassessed'
    # Revoking explicit grade authority prevents replay, even though an assignment
    # still carries ordinary assessment scope and the result already exists.
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.school_id==ids['school'],AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='assessment.grade')):grant.state='revoked'
    assert client.post(path(ids)+f'/statements/{row["id"]}/finalize',headers=h,json=payload).status_code==403
    history=client.get(path(ids)+f'/statements/{row["id"]}/revisions').json()
    assert history['total']==2
