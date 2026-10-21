"""Actual application routes and governance/protected-case adapters, no mock ports."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from spesped.contexts.identity.models import AuthorityGrant
from spesped.contexts.safeguarding.ports import ReviewedRuleContext
from spesped.errors import DomainError
from spesped.main import create_app
from test_safeguarding import env, setup, post, base, contact
from test_protected_rule_context import configured, reviewed_profile, trigger, prefix


def case_url(ids, case):
    return base(ids) + '/cases/' + case['id']


def test_application_registers_actual_contexts_without_test_router_installation(env):
    _, factory, _, _, _, prior = env
    app = create_app(prior.state.settings, factory)
    paths = app.openapi()['paths']
    for suffix in ('/support-cases/{case_id}', '/education-plans/{plan_id}', '/safeguarding/cases/{case_id}'):
        assert sum(path.endswith(suffix) for path in paths) == 1
    assert callable(app.state.evidence_goal_validator)
    assert callable(app.state.governance_case_scope_resolver)
    assert callable(app.state.governance_evidence_validator)
    assert callable(app.state.safeguarding_rule_context)


def test_case_rule_projection_preserves_actual_obligations_and_recall(configured):
    env, case, headers = configured
    client, _, ids, _, _, _ = env
    rule, profile = reviewed_profile(env, headers)
    task = trigger(env, case, headers, profile)
    path = case_url(ids, case)
    result = client.get(path)
    assert result.status_code == 200, result.text
    context = result.json()['rule_context']
    assert context['state'] == 'available'
    assert context['legal_completeness'] == 'not_assessed'
    obligation, = context['obligations']
    assert obligation['id'] == task['id']
    assert obligation['source']['profile_id'] == profile['id']
    assert obligation['source']['requirement_version_id'] == rule['id']
    assert obligation['required_action'] == rule['required_action']
    assert 'notification_requirements' not in context
    assert result.json()['actual_contacts'] == []
    post(client, prefix(ids) + '/requirement-versions/' + rule['id'] + '/withdraw', {
        'expected_version': rule['version'], 'rationale': 'Synthetic rule withdrawn after source review',
    }, headers)
    recalled = client.get(path).json()
    assert recalled['rule_context']['state'] == 'review_required'
    obligation, = recalled['rule_context']['obligations']
    assert obligation['source']['state'] == 'withdrawn'
    assert obligation['required_action'] is None and obligation['required_document_types'] == []
    assert obligation['state'] == task['state'] and recalled['actual_contacts'] == []


def test_unavailable_or_denied_optional_rules_do_not_hide_authorized_case(configured):
    env, case, headers = configured
    client, factory, ids, _, _, app = env
    _, profile = reviewed_profile(env, headers)
    trigger(env, case, headers, profile)
    path = case_url(ids, case)
    with factory.begin() as db:
        grant = db.scalar(select(AuthorityGrant).where(AuthorityGrant.school_id == ids['school'],
            AuthorityGrant.user_id == ids['teacher'], AuthorityGrant.case_id == case['id'],
            AuthorityGrant.action == 'governance.case.read'))
        grant.state = 'revoked'
    unavailable = ReviewedRuleContext(state='unavailable').model_dump(mode='json')
    response = client.get(path)
    assert response.status_code == 200 and response.json()['rule_context'] == unavailable
    # Invalid or temporarily unavailable optional metadata has the same safe
    # projection; it never turns known actual actions into fulfilled duties.
    def failed(*args):
        raise DomainError('rule_context_unavailable', 'Synthetic provider unavailable', 503)
    for resolver in (None, lambda *args: {'approved': True}, failed):
        app.state.safeguarding_rule_context = resolver
        response = client.get(path)
        assert response.status_code == 200 and response.json()['rule_context'] == unavailable
    recorded = post(client, path + '/actual-contacts', contact(case['version']), headers, 201)
    assert len(recorded['actual_contacts']) == 1
    assert client.get(path).json()['rule_context'] == unavailable
    # Governance being optional must never weaken the owning case permission.
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.case_id == case['id'],
                AuthorityGrant.action == 'safeguarding.case.read')):
            grant.state = 'revoked'
    assert client.get(path).status_code == 403


def test_multiple_profile_sources_and_unresolved_inputs_survive_http_projection(configured):
    env, case, headers = configured
    client, _, ids, _, _, _ = env
    _, old = reviewed_profile(env, headers, start='2020-01-01', end='2025-12-31')
    old_task = trigger(env, case, headers, old, occurred_at='2020-01-01T12:00:00Z')
    _, new = reviewed_profile(env, headers, conditions=[{'fact': 'support_entitlement', 'equals': True}], start='2026-01-01')
    new_task = trigger(env, case, headers, new)
    context = client.get(case_url(ids, case)).json()['rule_context']
    assert context['state'] == 'review_required'
    obligations = {item['id']: item for item in context['obligations']}
    assert obligations[old_task['id']]['source']['profile_id'] == old['id']
    assert obligations[new_task['id']]['source']['profile_id'] == new['id']
    assert obligations[new_task['id']]['required_action'] is None
    assert obligations[new_task['id']]['unresolved_inputs'] == ['support_entitlement']


def test_governance_document_action_resolves_current_protected_snapshot(configured):
    env, case, headers = configured
    client, _, ids, _, _, _ = env
    _, profile = reviewed_profile(env, headers)
    task = trigger(env, case, headers, profile)
    path = case_url(ids, case)
    current = client.get(path).json()
    snapshot = current['evidence_reference']
    action_path = prefix(ids) + '/obligations/' + task['id'] + '/actions'
    command = {'expected_version': task['version'], 'kind': 'document_upload', 'action_type': 'perspective_note',
               'description': 'Synthetic source snapshot only, no performed action claim',
               'occurred_at': '2026-10-01T12:00:00Z', 'evidence_references': [snapshot['reference_id']]}
    recorded = post(client, action_path, command, headers, 201)
    assert recorded['obligation']['state'] != 'satisfied'
    assert client.get(path).json()['actual_contacts'] == []
    updated = post(client, path + '/actual-contacts', contact(current['version']), headers, 201)
    assert updated['version'] > snapshot['revision']
    stale = client.post(action_path, headers=headers, json=command | {'expected_version': recorded['obligation']['version']})
    assert stale.status_code == 403, stale.text
    wrong = client.post(action_path, headers=headers, json=command | {
        'expected_version': recorded['obligation']['version'], 'evidence_references': [str(uuid4())]})
    assert wrong.status_code == 403, wrong.text
