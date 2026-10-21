"""BC07 transaction, deterministic retry and minimized audit/outbox helpers."""
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from spesped.audit import record_audit
from spesped.db import utcnow
from spesped.domain.approval import canonical_content_digest
from spesped.errors import DomainError
from .models import TeachingCommand, TeachingEvent


def conflict(message='Refresh and review the current version before retrying.'):
    return DomainError('revision_conflict',message,409)


def expected(row,command):
    if row.version != command.expected_version: raise conflict()


def replay(db,actor,school_id,operation,command,target):
    db.info['teaching_causation_id']=command.request_key
    digest=canonical_content_digest({'operation':operation,'target':target,'command':command.model_dump(mode='json')})
    prior=db.scalar(select(TeachingCommand).where(TeachingCommand.school_id == school_id,TeachingCommand.actor_id == actor.user_id,TeachingCommand.request_key == command.request_key))
    if prior:
        if prior.digest != digest or prior.operation != operation: raise DomainError('idempotency_conflict','This request key identifies different teaching content or scope.',409)
        return prior.target_id,digest
    return None,digest


def remember(db,actor,school_id,operation,command,digest,target):
    db.add(TeachingCommand(school_id=school_id,actor_id=actor.user_id,request_key=command.request_key,operation=operation,digest=digest,target_id=target))


def event(db,actor,row,action,**payload):
    db.flush()
    record_audit(db,actor,row.school_id,action,row.__tablename__,row.id)
    db.add(TeachingEvent(school_id=row.school_id,aggregate_id=row.id,aggregate_version=getattr(row,'version',1),event_type=action,actor_id=actor.user_id,payload=payload,correlation_id=db.info.setdefault('teaching_correlation_id',str(uuid4())),causation_id=db.info.get('teaching_causation_id')))


def mutate(db,operation):
    try:
        result=operation();db.commit();return result
    except StaleDataError:
        db.rollback();raise conflict() from None
    except DBAPIError as exc:
        db.rollback()
        state=getattr(exc.orig,'sqlstate',None)
        unique=state == '23505' or ('UNIQUE constraint failed' in str(exc.orig) if db.bind.dialect.name == 'sqlite' else False)
        if state in {'40001','40P01','55P03'} or unique:
            raise conflict('A concurrent command changed this record. Retry the same request key after refreshing.') from None
        raise
    except Exception:
        db.rollback();raise
