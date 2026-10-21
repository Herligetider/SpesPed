from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from spesped.auth import Actor, get_actor, require_authority
from spesped.db import get_db
from spesped.errors import DomainError
from .contracts import GatewayRuntime, GenerationRequest, PolicyCommand, ReleaseCommand, ReviewCommand, VersionCommand
from .models import GenerationAttempt, GenerationJob, ModelEvaluation, ModelRelease, ProcessingPolicy
from . import service

router = APIRouter(prefix='/api/v1/schools/{school_id}/ai', tags=['AI suggestions'])


def runtime(request: Request) -> GatewayRuntime:
    configured = getattr(request.app.state, 'ai_gateway', None)
    if configured is None:
        return GatewayRuntime(environment=request.app.state.settings.environment)
    if configured.environment != request.app.state.settings.environment:
        raise DomainError('gateway_environment_mismatch', 'The AI gateway configuration is unavailable.', 503)
    return configured


def job_view(job):
    return {key: getattr(job, key) for key in ('id', 'school_id', 'learner_id', 'version', 'state', 'purpose', 'policy_id', 'policy_version', 'release_id', 'release_digest', 'source_manifest', 'output', 'error_code', 'attempts', 'created_at', 'updated_at')} | {'manual_fallback_available': True}


def policy_view(policy):
    return {k: getattr(policy, k) for k in ('id', 'version', 'state', 'provider_key', 'configuration')}


def release_view(release):
    return {k: getattr(release, k) for k in ('id', 'version', 'state', 'provider_key', 'model_version', 'capability', 'template_version', 'output_schema_version', 'configuration_digest', 'reviewed_by', 'reviewed_at', 'evaluation_id', 'reviewed_evaluation_digest', 'review_rationale')}


def evaluation_view(evaluation, *, include_evidence=False):
    result = {k: getattr(evaluation, k) for k in ('id', 'release_id', 'state', 'suite_name', 'suite_digest', 'release_digest', 'artifact_digest', 'metrics', 'created_at')}
    if include_evidence:
        result['evidence'] = evaluation.evidence
    return result


@router.post('/policies', status_code=201)
def post_policy(school_id: UUID, command: PolicyCommand, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return policy_view(service.create_policy(db, actor, str(school_id), command, runtime(request)))


@router.post('/releases', status_code=201)
def post_release(school_id: UUID, command: ReleaseCommand, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return release_view(service.create_release(db, actor, str(school_id), command, runtime(request)))


@router.get('/configuration')
def get_configuration(school_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    sid = str(school_id)
    require_authority(db, actor, sid, 'platform.manage')
    result = {}
    for name, model, view in (('policies', ProcessingPolicy, policy_view), ('releases', ModelRelease, release_view)):
        query = select(model).where(model.school_id == sid)
        result[name] = {'items': [view(r) for r in db.scalars(query.order_by(model.created_at.desc(), model.id).limit(limit).offset(offset))], 'total': db.scalar(select(func.count()).select_from(model).where(model.school_id == sid))}
    return result


class EvaluationCommand(VersionCommand):
    policy_id: UUID
    suite_name: str = Field(min_length=1, max_length=100)


@router.post('/releases/{release_id}/evaluations', status_code=201)
def post_evaluation(school_id: UUID, release_id: UUID, command: EvaluationCommand, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return evaluation_view(service.evaluate_release(db, actor, str(school_id), str(release_id), command.expected_version, str(command.policy_id), command.suite_name, runtime(request)), include_evidence=True)


@router.get('/evaluations')
def get_evaluations(school_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    sid = str(school_id)
    require_authority(db, actor, sid, 'platform.manage')
    return {'items': [evaluation_view(e) for e in db.scalars(select(ModelEvaluation).where(ModelEvaluation.school_id == sid).order_by(ModelEvaluation.created_at.desc(), ModelEvaluation.id).limit(limit).offset(offset))], 'total': db.scalar(select(func.count()).select_from(ModelEvaluation).where(ModelEvaluation.school_id == sid))}


@router.get('/evaluations/{evaluation_id}')
def read_evaluation(school_id: UUID, evaluation_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    require_authority(db, actor, sid, 'platform.manage')
    evaluation = db.scalar(select(ModelEvaluation).where(ModelEvaluation.school_id == sid, ModelEvaluation.id == str(evaluation_id)))
    if evaluation is None:
        from spesped.errors import access_denied
        raise access_denied()
    return evaluation_view(evaluation, include_evidence=True)


@router.post('/releases/{release_id}/review')
def post_review(school_id: UUID, release_id: UUID, command: ReviewCommand, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return release_view(service.review_release(db, actor, str(school_id), str(release_id), command))


@router.post('/configuration/{kind}/{record_id}/revoke')
def post_revoke(school_id: UUID, kind: str, record_id: UUID, command: VersionCommand, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    record = service.revoke_configuration(db, actor, str(school_id), kind, str(record_id), command.expected_version)
    return {'id': record.id, 'version': record.version, 'state': record.state}


@router.post('/jobs', status_code=201)
def post_job(school_id: UUID, command: GenerationRequest, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return job_view(service.create_job(db, actor, str(school_id), command, runtime(request)))


@router.get('/jobs/{job_id}')
def read_job(school_id: UUID, job_id: UUID, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    job = service.get_job(db, actor, str(school_id), str(job_id), runtime(request))
    attempts = db.scalars(select(GenerationAttempt).where(GenerationAttempt.job_id == job.id).order_by(GenerationAttempt.number)).all()
    return job_view(job) | {'attempt_history': [{k: getattr(a, k) for k in ('number', 'state', 'started_at', 'finished_at', 'latency_ms', 'error_code', 'unsupported_source_count')} for a in attempts]}


@router.post('/jobs/{job_id}/run')
def post_run(school_id: UUID, job_id: UUID, command: VersionCommand, request: Request, actor: Actor = Depends(get_actor)):
    job = service.run_job(request.app.state.session_factory, actor, str(school_id), str(job_id), command.expected_version, runtime(request))
    result = job_view(job)
    if job.state != 'succeeded':
        result.pop('source_manifest', None)
    return result


@router.post('/jobs/{job_id}/cancel')
def post_cancel(school_id: UUID, job_id: UUID, command: VersionCommand, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    job = service.cancel_job(db, actor, str(school_id), str(job_id), command.expected_version, runtime(request))
    return {'id': job.id, 'version': job.version, 'state': job.state, 'manual_fallback_available': True}


@router.post('/jobs/{job_id}/expire')
def post_expire(school_id: UUID, job_id: UUID, command: VersionCommand, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    job = service.expire_job(db, actor, str(school_id), str(job_id), command.expected_version)
    return {'id': job.id, 'version': job.version, 'state': job.state, 'error_code': job.error_code, 'manual_fallback_available': True}


@router.get('/metrics')
def get_metrics(school_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    require_authority(db, actor, sid, 'platform.manage')
    counts = dict(db.execute(select(GenerationJob.state, func.count()).where(GenerationJob.school_id == sid).group_by(GenerationJob.state)).all())
    attempts = db.execute(select(func.count(), func.avg(GenerationAttempt.latency_ms), func.sum(GenerationAttempt.unsupported_source_count)).where(GenerationAttempt.school_id == sid)).one()
    total = sum(counts.values())
    return {'jobs_by_state': counts, 'total_jobs': total, 'failure_rate': (counts.get('failed', 0)+counts.get('unavailable', 0))/total if total else None, 'attempt_count': attempts[0], 'mean_latency_ms': float(attempts[1]) if attempts[1] is not None else None, 'unsupported_source_count': attempts[2] or 0}
