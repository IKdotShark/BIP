from contextlib import asynccontextmanager
from fastapi import FastAPI
from models import Base
from container import container
from config import settings
import logging
from sqlalchemy.ext.asyncio import AsyncEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для инициализации и очистки ресурсов"""

    # === Startup ===
    logger.info("Starting application...")

    # Создаём ресурсы вручную для контроля жизненного цикла
    db_engine: AsyncEngine = container.db_engine()
    redis_client = await container.redis_client()

    # Создаём таблицы БД
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    # Передаём ресурсы в контейнер через конфигурацию (опционально)
    # Или просто используем их напрямую в контроллерах

    # Создаём контроллеры с явной передачей зависимостей
    redis_repo = container.redis_repository(client=redis_client)
    db_repo = container.db_repository(session_factory=container.db_session_factory(bind=db_engine))

    redis_service = container.redis_api_service(redis_repo=redis_repo)
    notes_service = container.notes_service(db_repo=db_repo, redis_repo=redis_repo)

    redis_ctrl = container.redis_controller(service=redis_service)
    notes_ctrl = container.notes_controller(service=notes_service)

    app.include_router(redis_ctrl.router)
    app.include_router(notes_ctrl.router)

    logger.info("Application started")

    yield  # Приложение работает здесь

    # === Shutdown ===
    logger.info("Shutting down...")
    await redis_client.close()
    await db_engine.dispose()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/")
    async def root():
        return {"service": settings.APP_NAME, "docs": "/docs"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)