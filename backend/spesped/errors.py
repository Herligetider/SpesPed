from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException


class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def access_denied():
    return DomainError("access_denied", "You do not have access to this operation.", 403)


def install_error_handlers(app: FastAPI):
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo submitted values, password, pupil text or Pydantic exception contexts.
        details = [{"field": ".".join(str(x) for x in e["loc"]), "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"error": {"code": "validation_error", "message": "Check the submitted fields.", "details": details}}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse({"error": {"code": "request_error", "message": "The request could not be completed."}}, status_code=exc.status_code)

    @app.exception_handler(StaleDataError)
    async def stale_error(request: Request, exc: StaleDataError):
        return JSONResponse({"error": {"code": "version_conflict", "message": "This record changed. Reload and try again."}}, status_code=409)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse({"error": {"code": "conflict", "message": "The requested change conflicts with existing data."}}, status_code=409)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return JSONResponse({"error": {"code": "internal_error", "message": "The request could not be completed."}}, status_code=500)
