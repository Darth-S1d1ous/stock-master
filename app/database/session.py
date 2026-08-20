from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.settings import get_database_settings

settings = get_database_settings()

# template for database engine. Not an instance
engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    echo=settings.database_echo,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={
        "timeout": 10,
        "server_settings": {
            "application_name": "stock-master-bot",
        },
    },
)

# a factory function to create a database session
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)

async def get_database_session() -> AsyncIterator[AsyncSession]:
    """
    create a database session.
    """

    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

async def close_database_engine() -> None:
    """
    close the database engine.
    """
    await engine.dispose()
    