import hmac
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, ClassVar
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories import StockDataRepository
from app.database.session import AsyncSessionFactory
from app.database.thesis_repositories import ThesisRepository
from app.services.thesis_monitoring_service import ThesisMonitoringService


class ApiSecuritySettings(BaseSettings):
    """Authentication settings for the single-user MVP API."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_user_id: UUID
    api_bearer_token: SecretStr = Field(min_length=32, max_length=128)

    @field_validator("api_user_id")
    @classmethod
    def reject_nil_user_id(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError("API_USER_ID cannot be the nil UUID")
        return value

# initialize the settings once
@lru_cache
def get_api_security_settings() -> ApiSecuritySettings:
    """Return the API security settings."""
    return ApiSecuritySettings.model_validate({})


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Identity established by the authentication dependency."""

    id: UUID

# HTTPBearer parses the header "Authorization: Bearer <token>"
_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description=(
        "Static Bearer token authentication for the single-user MVP."
    ),
)

def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer_scheme)],
    settings:    Annotated[ApiSecuritySettings, Depends(get_api_security_settings)]
) -> AuthenticatedUser:
    """Authenticate the request and return its trusted user identity."""

    if (credentials is None or credentials.scheme.lower() != "bearer"):
        raise _authentication_error()

    supplied_token = credentials.credentials
    expected_token = settings.api_bearer_token.get_secret_value()

    if not hmac.compare_digest(supplied_token.encode("utf-8"), expected_token.encode("utf-8")):
        raise _authentication_error()

    return AuthenticatedUser(id=settings.api_user_id)

async def get_database_session() -> AsyncIterator[AsyncSession]:
    """Provide one transaction-scoped database session per request.

    Repository methods only flush changes. This dependency commits the
    transaction when the request succeeds and rolls it back when an
    exception escapes the route handler.
    """

    async with AsyncSessionFactory() as session, session.begin():
        yield session

def get_stock_data_repository(
    session: Annotated[AsyncSession, Depends(get_database_session)]
) -> StockDataRepository:
    """Build the stock-data repository for the current transaction."""

    return StockDataRepository(session)

def get_thesis_repository(
    session: Annotated[AsyncSession, Depends(get_database_session)]
) -> ThesisRepository:
    """Build the thesis repository for the current transaction."""

    return ThesisRepository(session)

def get_thesis_monitoring_service(
    stock_data_repository: Annotated[StockDataRepository, Depends(get_stock_data_repository)],
    thesis_repository:     Annotated[ThesisRepository, Depends(get_thesis_repository)],
) -> ThesisMonitoringService:
    """Build the deterministic thesis-monitoring application service."""

    return ThesisMonitoringService(
        stock_data_repo=stock_data_repository,
        thesis_repo=thesis_repository,
    )

def _authentication_error() -> HTTPException:
    """Return a generic authentication failure without leaking details."""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "authentication_required",
            "message": "Valid authentication credentials are required.",
        },
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )

CurrentUser = Annotated[
    AuthenticatedUser,
    Depends(get_current_user),
]

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_database_session),
]

StockDataRepositoryDependency = Annotated[
    StockDataRepository,
    Depends(get_stock_data_repository),
]

ThesisRepositoryDependency = Annotated[
    ThesisRepository,
    Depends(get_thesis_repository),
]

ThesisMonitoringServiceDependency = Annotated[
    ThesisMonitoringService,
    Depends(get_thesis_monitoring_service),
]