"""Current identity metadata for a pupil's document editing workspace.

Names are returned only after native action authorization. No contact details,
relationship restrictions or protected-case grants form part of this port.
"""
from contextlib import contextmanager
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from spesped.auth import Actor, active_at, require_learner_access, school_today
from spesped.errors import DomainError
from . import models as m

MAX_CANDIDATES = 1000

@contextmanager
def reader(db):
    if any(type(row).__module__.startswith('spesped.contexts.') for row in db.new | db.dirty | db.deleted):
        raise DomainError('dependency_pending', 'Flush or roll back pending dependencies before reading choices.', 409)
    with db.no_autoflush:
        with Session(bind=db.connection(), join_transaction_mode='rollback_only', autoflush=False, expire_on_commit=False) as fresh:
            fresh.info.update(db.info)
            yield fresh

def bounded(db, statement):
    rows = list(db.execute(statement.limit(MAX_CANDIDATES + 1)))
    if len(rows) > MAX_CANDIDATES:
        raise DomainError('choice_limit', 'Narrow the selection before listing more than 1000 source candidates.', 422)
    return rows

def json_member(db, column, value):
    """Exact JSON array membership on the two supported database engines."""
    if db.bind.dialect.name == 'postgresql':
        elements = func.json_array_elements_text(column).table_valued('value').render_derived()
    else:
        elements = func.json_each(column).table_valued('value')
    return select(1).select_from(elements).where(elements.c.value == value).exists()

def guardians(db, actor, school_id, learner_id, query=None):
    with reader(db) as fresh:
        require_learner_access(fresh, actor, school_id, learner_id, 'documents.write')
        today = school_today(fresh.get(m.School, school_id))
        statement = select(m.GuardianRelationship, m.UserAccount).join(m.UserAccount, m.UserAccount.id == m.GuardianRelationship.guardian_user_id).where(
            m.GuardianRelationship.school_id == school_id, m.GuardianRelationship.learner_id == learner_id,
            *active_at(m.GuardianRelationship, today))
        if query: statement = statement.where(m.UserAccount.display_name.icontains(query, autoescape=True))
        rows = bounded(fresh, statement.order_by(m.UserAccount.display_name, m.GuardianRelationship.id))
        return [dict(relationship_id=r.id, guardian_user_id=u.id, display_name=u.display_name, version=r.version,
            state='eligible_proposal' if u.state == 'active' and r.parental_responsibility and r.information_rights in {'full', 'allowed', 'yes'} and not r.restrictions and r.source_reference else 'unresolved',
            disclosure='not_authorized') for r, u in rows]

def staff(db, actor, school_id, learner_id, purpose, query=None):
    action = {'owner': 'documents.write', 'contributor': 'documents.contribute'}[purpose]
    with reader(db) as fresh:
        require_learner_access(fresh, actor, school_id, learner_id, 'documents.write')
        today = school_today(fresh.get(m.School, school_id))
        # Limit inventory to people holding a relevant current assignment or
        # explicit non-case grant, then recheck full native authorization.
        grants = select(m.AuthorityGrant.user_id).where(m.AuthorityGrant.school_id == school_id,
            m.AuthorityGrant.action == action, m.AuthorityGrant.case_id.is_(None),
            (m.AuthorityGrant.learner_id.is_(None) | (m.AuthorityGrant.learner_id == learner_id)), *active_at(m.AuthorityGrant, today))
        assignments = select(m.StaffAssignment.user_id).where(m.StaffAssignment.school_id == school_id,
            m.StaffAssignment.learner_id == learner_id, *active_at(m.StaffAssignment, today), json_member(fresh,m.StaffAssignment.actions,action))
        statement = select(m.UserAccount).join(m.SchoolMembership, m.SchoolMembership.user_id == m.UserAccount.id).where(
            m.SchoolMembership.school_id == school_id, *active_at(m.SchoolMembership, today), m.UserAccount.state == 'active',
            (m.UserAccount.id.in_(grants) | m.UserAccount.id.in_(assignments)))
        if query: statement = statement.where(m.UserAccount.display_name.icontains(query, autoescape=True))
        rows = bounded(fresh, statement.order_by(m.UserAccount.display_name, m.UserAccount.id))
        items = []
        for (user,) in rows:
            try:
                require_learner_access(fresh, Actor(user.id), school_id, learner_id, action)
            except DomainError as exc:
                if exc.status_code != 403: raise
                continue
            current = fresh.scalars(select(m.StaffAssignment).where(m.StaffAssignment.school_id == school_id,
                m.StaffAssignment.learner_id == learner_id, m.StaffAssignment.user_id == user.id,
                *active_at(m.StaffAssignment, today)).order_by(m.StaffAssignment.id))
            matching = next((v for v in current if action in v.actions), None)
            items.append(dict(user_id=user.id, display_name=user.display_name, purpose=purpose, action=action,
                state='eligible', assignment_purpose=matching.purpose if matching else None))
        return items
