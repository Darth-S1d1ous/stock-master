from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.dependencies import get_api_security_settings
from app.api.routes.events import router as events_router
from app.api.routes.theses import router as theses_router
from app.database.session import close_database_engine

_API_TITLE = "Stock Master Bot API"
_API_VERSION = "0.1.0"

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate configuration and release shared resources."""

    del app

    # Fail during startup rather than on the first authenticated request
    # when required API security settings are missing or invalid.
    _ = get_api_security_settings()

    try:
        yield
    finally:
        await close_database_engine()

app = FastAPI(
    title=_API_TITLE,
    version=_API_VERSION,
    description=("Auditable investment-thesis monitoring API for deterministic stock events and evidence."),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    debug=False,
)

app.include_router(theses_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")

@app.get(
    "/health/live",
    tags=["health"],
    summary="Liveness check",
    response_model=dict[str, str],
)
async def liveness() -> dict[str, str]:
    """Return process liveness without accessing external services."""

    return {
        "status": "ok",
    }


# ------ Exception Handlers ------
@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(
    request: Request,
    exception: StarletteHTTPException,
) -> JSONResponse:
    """Return a stable API error envelope for HTTP failures."""

    del request

    code, message = _normalize_http_error(exception)

    return JSONResponse(
        status_code=exception.status_code,
        content={
            "code": code,
            "message": message,
        },
        headers=exception.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    """Return validation failures without reflecting request values."""

    del request

    fields = _invalid_request_fields(exception)

    if fields:
        message = (
            "The request contains invalid fields: "
            f"{', '.join(fields)}."
        )
    else:
        message = "The request is invalid."

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "code": "request_validation_failed",
            "message": message,
        },
    )


def _normalize_http_error(
    exception: StarletteHTTPException,
) -> tuple[str, str]:
    detail = exception.detail

    if isinstance(detail, dict):
        detail_mapping = cast(dict[object, object], detail)
        code = detail_mapping.get("code")
        message = detail_mapping.get("message")

        if isinstance(code, str) and isinstance(message, str):
            return (
                _safe_error_code(code),
                _safe_error_message(message),
            )

    return _default_http_error(
        status_code=exception.status_code,
    )


def _default_http_error(
    *,
    status_code: int,
) -> tuple[str, str]:
    errors = {
        status.HTTP_400_BAD_REQUEST: (
            "bad_request",
            "The request could not be processed.",
        ),
        status.HTTP_401_UNAUTHORIZED: (
            "authentication_required",
            "Valid authentication credentials are required.",
        ),
        status.HTTP_403_FORBIDDEN: (
            "forbidden",
            "The requested operation is not permitted.",
        ),
        status.HTTP_404_NOT_FOUND: (
            "resource_not_found",
            "The requested resource was not found.",
        ),
        status.HTTP_405_METHOD_NOT_ALLOWED: (
            "method_not_allowed",
            "The HTTP method is not allowed for this resource.",
        ),
        status.HTTP_409_CONFLICT: (
            "conflict",
            "The request conflicts with the current resource state.",
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            "request_validation_failed",
            "The request is invalid.",
        ),
        status.HTTP_500_INTERNAL_SERVER_ERROR: (
            "internal_server_error",
            "The server could not complete the request.",
        ),
    }

    return errors.get(
        status_code,
        (
            "http_error",
            "The request could not be completed.",
        ),
    )


def _invalid_request_fields(
    exception: RequestValidationError,
) -> list[str]:
    fields: set[str] = set()

    errors = cast(list[dict[str, object]], exception.errors())
    for error in errors:
        location = error.get("loc")
        if not isinstance(location, (tuple, list)):
            continue
        location_parts = cast(tuple[object, ...] | list[object], location)

        public_parts = [
            str(part)
            for part in location_parts
            if (
                part not in {"body", "path", "query", "header", "cookie"}
                and isinstance(part, (str, int))
            )
        ]

        if public_parts:
            fields.add(".".join(public_parts))

    return sorted(fields)


def _safe_error_code(
    value: str,
) -> str:
    normalized = value.strip().lower()

    if (
        not normalized
        or len(normalized) > 100
        or not normalized[0].isalpha()
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
            for character in normalized
        )
    ):
        return "http_error"

    return normalized


def _safe_error_message(
    value: str,
) -> str:
    normalized = " ".join(value.split())

    if not normalized:
        return "The request could not be completed."

    return normalized[:500]