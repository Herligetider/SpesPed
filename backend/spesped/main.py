from uuid import UUID

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from spesped.config import Settings, get_settings
from spesped.db import make_session_factory
from spesped.errors import install_error_handlers
from spesped.contexts.identity.router import router as identity_router
from spesped.contexts.evidence.router import router as evidence_router
from spesped.contexts.platform.router import router as platform_router
from spesped.contexts.governance.router import router as governance_router
from spesped.contexts.entitlements.router import router as entitlements_router
from spesped.contexts.plans.router import router as plans_router
from spesped.contexts.safeguarding.router import router as safeguarding_router
from spesped.contexts.teaching.router import router as teaching_router
from spesped.contexts.curriculum.router import router as curriculum_router
from spesped.contexts.assessment.router import router as assessment_router
from spesped.contexts.administration.router import router as administration_router
from spesped.assembly import configure_contexts


class PrivateResponseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Read/access-denial metadata is separate from successful command records.
        # No request body, query string, email, password or pupil prose is recorded.
        actor = getattr(request.state, "actor", None)
        params = request.path_params
        if actor and "school_id" in params and (response.status_code == 403 or (request.method == "GET" and response.status_code == 200 and "/learners" in request.url.path)):
            from spesped.contexts.identity.models import AuditRecord, School
            try:
                school_id = str(UUID(str(params["school_id"])))
                target_id = str(UUID(str(params.get("learner_id", school_id))))
            except ValueError:
                return response
            with request.app.state.session_factory.begin() as db:
                known_school = school_id if db.get(School, school_id) else None
                db.add(AuditRecord(actor_id=actor.user_id, school_id=known_school, action="access.denied" if response.status_code == 403 else "learner.read", target_type="learner" if "learner_id" in params else "school", target_id=target_id, outcome="denied" if response.status_code == 403 else "success"))
        return response


def create_app(settings: Settings | None = None, session_factory=None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SpesPed", docs_url=None if settings.environment == "production" else "/docs", redoc_url=None)
    app.state.settings = settings
    app.state.session_factory = session_factory or make_session_factory(settings.database_url)
    configure_contexts(app, settings)
    install_error_handlers(app)
    app.add_middleware(PrivateResponseMiddleware)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    app.include_router(identity_router)
    app.include_router(evidence_router)
    app.include_router(platform_router)
    app.include_router(governance_router)
    app.include_router(entitlements_router)
    app.include_router(plans_router)
    app.include_router(safeguarding_router)
    app.include_router(teaching_router)
    app.include_router(curriculum_router)
    app.include_router(assessment_router)
    app.include_router(administration_router)
    return app


app = create_app()
