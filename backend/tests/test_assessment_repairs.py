"""Regression proof for J10-R1 nested freshness and J10-R2 event semantics."""
from datetime import timedelta,date,datetime
from uuid import UUID
import pytest
from sqlalchemy import select,func
from assessment_fixtures import *
from test_assessment import evidence_reference,competence,exact_progress
from spesped.contexts.assessment import models as m
from spesped.db import utcnow


def confirm(client,ids,h,row):
    for step in ('submit','confirm'):
        response=client.post(path(ids)+f'/progress-reviews/{row["id"]}/review',headers=h,json=exact_progress(row,transition=step));assert response.status_code==200,response.text;row=response.json()
    return row

def progress_ref(row):return {'kind':'progress_review','id':row['id'],'revision':row['content']['number']}
def final_payload(row):return expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic exact statement review',contribution_ids=[c['id'] for c in row['contributions']])
def contextual_basis(binding,review):return [competence(binding),{'reference':progress_ref(review),'curriculum_goal_code':'READ1','role':'iop_context','relevance':'Explicit historical progress context, separate from subject competence'}]


def test_late_evidence_propagates_nested_sources_and_blocks_finalization_replay(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);goal_id,_=ordinary_goal(client,ids,h);observed=observation(client,ids,h,goal_id)
    primary=confirm(client,ids,h,progress(client,ids,h,goal_id))
    secondary=confirm(client,ids,h,progress(client,ids,h,goal_id,references=[progress_ref(primary)]))
    sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h)
    content=statement_content(basis=contextual_basis(binding,secondary))
    draft=statement(client,ids,h,sc,content=content)
    finalized=statement(client,ids,h,sc,content=content)
    finalize_key=final_payload(finalized)
    response=client.post(path(ids)+f'/statements/{finalized["id"]}/finalize',headers=h,json=finalize_key);assert response.status_code==200,response.text;finalized=response.json()
    # Keep an exact creation request to verify replay uses live dependency state.
    replay_payload=retry(learner_id=ids['a'],scheme_revision_id=sc['content']['id'],subject='reading',assessment_type='half_year',starts_on='2026-10-01',ends_on='2026-10-21',content=content)
    response=client.post(path(ids)+'/statements',headers=h,json=replay_payload);assert response.status_code==201,response.text
    replay_id=response.json()['id']
    late=observation(client,ids,h,goal_id,occurred_at=observed['occurred_at'],observation='Synthetic late contradictory independent attempt',support='Synthetic greater support')
    primary_current=client.get(path(ids)+f'/progress-reviews/{primary["id"]}').json()
    assert primary_current['source_status']=='review_required' and primary_current['content']==primary['content']
    assert primary_current['snapshot_digest']==primary['snapshot_digest'] and late['revision_id'] in primary_current['late_evidence_revision_ids']
    nested=client.get(path(ids)+f'/progress-reviews/{secondary["id"]}').json()
    assert nested['source_status']=='review_required' and nested['content']==secondary['content']
    assert nested['review_dependencies'][0]['reference']['id']==primary['id']
    assert late['revision_id'] in nested['review_dependencies'][0]['late_evidence_revision_ids']
    inherited=client.get(path(ids)+f'/statements/{draft["id"]}').json()
    assert inherited['source_status']=='review_required' and inherited['review_dependencies'][0]['reference']['id']==secondary['id']
    assert 'source_review_required' in inherited['unresolved']
    response=client.post(path(ids)+f'/statements/{draft["id"]}/finalize',headers=h,json=final_payload(inherited));assert response.status_code==409,response.text
    assert client.get(path(ids)+f'/statements/{draft["id"]}').json()['state']!='finalized'
    replay=client.post(path(ids)+'/statements',headers=h,json=replay_payload);assert replay.status_code==201,replay.text
    assert replay.json()['id']==replay_id and replay.json()['source_status']=='review_required'
    # Historical finalized judgement/approval survive, with an explicit warning.
    response=client.post(path(ids)+f'/statements/{finalized["id"]}/finalize',headers=h,json=finalize_key);assert response.status_code==200,response.text
    historical=response.json()
    assert historical['state']=='finalized' and historical['content_digest']==finalized['content_digest']
    assert historical['finalization']==finalized['finalization'] and historical['source_status']=='review_required'
    new=statement(client,ids,h,sc,content=content)
    assert new['state']=='needs_basis' and new['source_status']=='review_required' and 'source_review_required' in new['unresolved']
    history=client.get(path(ids)+f'/statements/{draft["id"]}/revisions').json()
    assert history['items'][0]['source_status']=='review_required'
    new_review=progress(client,ids,h,goal_id,references=[progress_ref(primary)],finding=finding(comparison_limitations=['Support changed; prior professional review needs reassessment']))
    assert new_review['source_status']=='review_required' and new_review['review_dependencies'][0]['reference']['id']==primary['id']
    response=client.post(path(ids)+f'/progress-reviews/{new_review["id"]}/review',headers=h,json=exact_progress(new_review,transition='submit'));assert response.status_code==409,response.text


def test_source_correction_invalidates_prior_review_chain_without_rewriting_history(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);goal_id,_=ordinary_goal(client,ids,h);observed=observation(client,ids,h,goal_id)
    primary=confirm(client,ids,h,progress(client,ids,h,goal_id));secondary=confirm(client,ids,h,progress(client,ids,h,goal_id,references=[progress_ref(primary)]))
    sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h);draft=statement(client,ids,h,sc,content=statement_content(basis=contextual_basis(binding,secondary)))
    payload={'learner_id':ids['a'],'goal_revision_id':goal_id,'occurred_at':observed['occurred_at'],'observation':'Synthetic attributed correction of the original fact','support':'Synthetic corrected support','interpretation':None,'next_step':None,'input_method':'manual','transcript_reviewed':False}
    response=client.post(base(ids)+f'/teaching/observations/{observed["id"]}/corrections',headers=h,json=expected(observed,save=True,reason='Synthetic correction of recorded evidence',content=payload));assert response.status_code==200,response.text
    for review in (primary,secondary):
        current=client.get(path(ids)+f'/progress-reviews/{review["id"]}').json()
        assert current['source_status']=='unavailable' and current['content'] is None
    inherited=client.get(path(ids)+f'/statements/{draft["id"]}').json();assert inherited['source_status']=='unavailable' and inherited['content'] is None
    with factory() as db:
        assert db.get(m.ProgressReview,primary['id']).snapshot_digest==primary['snapshot_digest']
        assert db.get(m.ProgressRevision,secondary['content']['id']).finding==secondary['content']['finding']
        assert db.get(m.Statement,draft['id']).state!='finalized'


def test_fresh_human_review_handles_late_basis_instead_of_clearing_old_warning(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);goal_id,_=ordinary_goal(client,ids,h);observed=observation(client,ids,h,goal_id)
    primary=confirm(client,ids,h,progress(client,ids,h,goal_id))
    observation(client,ids,h,goal_id,occurred_at=observed['occurred_at'],observation='Synthetic new contrary result',support='Synthetic additional support')
    fresh=confirm(client,ids,h,progress(client,ids,h,goal_id,finding=finding(comparison_limitations=['Support differed; both observations reviewed'],contradictory_evidence=['Independent attempts differed'],outcome='more_information')))
    sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h)
    statement_row=statement(client,ids,h,sc,content=statement_content(basis=contextual_basis(binding,fresh)))
    response=client.post(path(ids)+f'/statements/{statement_row["id"]}/finalize',headers=h,json=final_payload(statement_row));assert response.status_code==200,response.text
    assert client.get(path(ids)+f'/progress-reviews/{primary["id"]}').json()['review_required']
    assert response.json()['source_status']=='current'


def test_events_distinguish_actual_occurrence_recording_correlation_and_replay(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);ins,_=instrument(client,ids,h);row=planned(client,ids,h,ins)
    actual=utcnow()-timedelta(hours=2)
    payload=expected(row,occurred_at=actual.isoformat())
    response=client.post(path(ids)+f'/administrations/{row["id"]}/start',headers=h,json=payload);assert response.status_code==200,response.text;row=response.json()
    row=recorded(client,ids,h,row)
    with factory() as db:
        events=list(db.scalars(select(m.AssessmentEvent).where(m.AssessmentEvent.school_id==ids['school']).order_by(m.AssessmentEvent.created_at,m.AssessmentEvent.id)))
        assert events and all(e.schema_version==1 and UUID(e.correlation_id) and e.causation_id and e.occurred_at.tzinfo and e.recorded_at.tzinfo and e.occurred_at<=e.recorded_at for e in events)
        started_event=next(e for e in events if e.event_type=='assessment.administration.started')
        assert started_event.occurred_at==actual and started_event.recorded_at>actual and started_event.causation_id==payload['request_key']
        assert started_event.created_at==started_event.recorded_at
        result_event=next(e for e in events if e.event_type=='assessment.result.recorded')
        assert result_event.occurred_at==datetime.fromisoformat(row['result']['occurred_at'])
        assert result_event.payload=={'result_revision_id':row['result']['id']}
        assert result_event.correlation_id!=started_event.correlation_id
        before=len(events)
    response=client.post(path(ids)+f'/administrations/{row["id"]}/start',headers=h,json=payload);assert response.status_code==200,response.text
    with factory() as db:assert db.scalar(select(func.count()).select_from(m.AssessmentEvent))==before


@pytest.mark.parametrize('certainty',['confirmed','disputed'])
def test_late_bc02_goal_evidence_propagates_its_exact_coordinate(assessment_env,certainty):
    client,factory,app,ids=assessment_env;h=login(client);goal_id,_=ordinary_goal(client,ids,h);observed=observation(client,ids,h,goal_id)
    primary=confirm(client,ids,h,progress(client,ids,h,goal_id))
    sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h);draft=statement(client,ids,h,sc,content=statement_content(basis=contextual_basis(binding,primary)))
    response=client.post(base(ids)+'/intake/notes',headers=h,json=retry(external_scope='manual',external_id=key(),sender='Synthetic staff reporter',document_type='goal_observation',received_at=utcnow().isoformat(),text='Synthetic late report contradicts an earlier supported attempt'))
    assert response.status_code==201,response.text
    proposal=client.get(base(ids)+f'/intake/{response.json()["id"]}/proposals').json()['items'][0]
    reviewed_source=client.post(base(ids)+f'/extraction-proposals/{proposal["id"]}/review',headers=h,json={'expected_version':proposal['version'],'outcome':'accepted','reason':'Synthetic source checked'})
    response=client.post(base(ids)+f'/extraction-proposals/{proposal["id"]}/confirm',headers=h,json={'expected_version':reviewed_source.json()['version'],'learner_id':ids['a'],'claim_type':'report','reporter':'Synthetic observer','source_type':'reported_information','certainty':certainty,'occurred_at':observed['occurred_at'],'goal_revision_id':goal_id,'topic':'goal_progress','excerpt_page':proposal['page'],'excerpt_start':proposal['span_start'],'excerpt_end':proposal['span_end']})
    assert response.status_code==201,response.text;late=response.json()
    exact='evidence:'+late['id']+':'+str(late['revision'])
    current=client.get(path(ids)+f'/progress-reviews/{primary["id"]}').json()
    assert current['source_status']=='review_required'
    if certainty=='confirmed':assert exact in current['late_evidence_revision_ids']
    else:assert current['evidence_availability_changed'] and exact not in current['late_evidence_revision_ids']
    inherited=client.get(path(ids)+f'/statements/{draft["id"]}').json()
    assert inherited['source_status']=='review_required'
    marker=inherited['review_dependencies'][0]
    if certainty=='confirmed':assert exact in marker['late_evidence_revision_ids']
    else:assert marker['evidence_availability_changed'] and exact not in marker['late_evidence_revision_ids']
    response=client.post(path(ids)+f'/statements/{draft["id"]}/finalize',headers=h,json=final_payload(inherited));assert response.status_code==409,response.text
