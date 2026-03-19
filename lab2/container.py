from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine
import redis.asyncio as redis

from config import settings
from repositories import DatabaseRepository, RedisRepository
from services import RedisApiService, NotesService
from controllers import RedisController, NotesController


class Container(containers.DeclarativeContainer):
    """DI контейнер"""

    # Простые фабричные провайдеры (без Resource)
    db_engine: providers.Factory[AsyncEngine] = providers.Factory(
        create_async_engine,
        url=settings.DB_URL,
        echo=False
    )

    db_session_factory = providers.Factory(
        async_sessionmaker,
        bind=db_engine,
        expire_on_commit=False
    )

    redis_client = providers.Factory(
        redis.from_url,
        url=settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False
    )

    # Repositories
    db_repository = providers.Factory(DatabaseRepository, session_factory=db_session_factory)
    redis_repository = providers.Factory(RedisRepository, client=redis_client)

    # Services
    redis_api_service = providers.Factory(RedisApiService, redis_repo=redis_repository)
    notes_service = providers.Factory(NotesService, db_repo=db_repository, redis_repo=redis_repository)

    # Controllers
    redis_controller = providers.Factory(RedisController, service=redis_api_service)
    notes_controller = providers.Factory(NotesController, service=notes_service)


container = Container()