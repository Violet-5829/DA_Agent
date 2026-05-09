from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import settings

_engine: AsyncEngine | None = None
_SessionFactory: async_sessionmaker | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL 未配置")
        _engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=settings.debug,
        )
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _SessionFactory


async def get_session():
    return get_session_factory()()


async def close_engine():
    global _engine, _SessionFactory
    if _engine:
        await _engine.dispose()
        _engine = None
        _SessionFactory = None
