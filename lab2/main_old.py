import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List, Any, Dict

# --- Dependencies & Config ---
from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import redis.asyncio as redis
from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings:
    REDIS_URL: str = "redis://localhost:6379"
    DB_URL: str = "sqlite+aiosqlite:///./notes.db"
    APP_NAME: str = "Redis API & Notes Service"

settings = Settings()
Base = declarative_base()

class NoteDBModel(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RedisKeys:
    NOTE_CONTENT = "note:content:{id}"
    NOTE_META = "note:meta:{id}"

class DatabaseRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def create_note(self, title: str, content: str) -> NoteDBModel:
        async with self.session_factory() as session:
            note = NoteDBModel(title=title, content=content)
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return note

    async def get_note(self, note_id: int) -> Optional[NoteDBModel]:
        async with self.session_factory() as session:
            result = await session.execute(text(f"SELECT * FROM notes WHERE id = {note_id}"))
            pass

        async with self.session_factory() as session:
            note = await session.get(NoteDBModel, note_id)
            return note

    async def update_note(self, note_id: int, title: str, content: str) -> Optional[NoteDBModel]:
        async with self.session_factory() as session:
            note = await session.get(NoteDBModel, note_id)
            if not note:
                return None
            note.title = title
            note.content = content
            note.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(note)
            return note

    async def delete_note(self, note_id: int) -> bool:
        async with self.session_factory() as session:
            note = await session.get(NoteDBModel, note_id)
            if not note:
                return False
            await session.delete(note)
            await session.commit()
            return True


class RedisRepository:
    def __init__(self, client: redis.Redis):
        self.client = client

    async def set_key(self, key: str, value: str, ex: Optional[int] = None):
        await self.client.set(key, value, ex=ex)

    async def get_key(self, key: str) -> Optional[str]:
        return await self.client.get(key)

    async def delete_key(self, key: str):
        await self.client.delete(key)

    async def expire_key(self, key: str, seconds: int):
        await self.client.expire(key, seconds)

    async def incr_key(self, key: str) -> int:
        return await self.client.incr(key)

    async def list_push(self, key: str, value: str):
        await self.client.lpush(key, value)

    async def list_get(self, key: str) -> List[str]:
        return await self.client.lrange(key, 0, -1)

    async def hash_set(self, key: str, field: str, value: str):
        await self.client.hset(key, field, value)

    async def hash_get_all(self, key: str) -> Dict[str, str]:
        data = await self.client.hgetall(key)
        return {k.decode(): v.decode() for k, v in data.items()}

    async def hash_increment(self, key: str, field: str, amount: int = 1) -> int:
        return await self.client.hincrby(key, field, amount)

    async def cache_note_content(self, note_id: int, content: str):
        key = RedisKeys.NOTE_CONTENT.format(id=note_id)
        await self.client.set(key, content)

    async def get_cached_note_content(self, note_id: int) -> Optional[str]:
        key = RedisKeys.NOTE_CONTENT.format(id=note_id)
        val = await self.client.get(key)
        return val.decode() if val else None

    async def delete_note_cache(self, note_id: int):
        content_key = RedisKeys.NOTE_CONTENT.format(id=note_id)
        meta_key = RedisKeys.NOTE_META.format(id=note_id)
        await self.client.delete(content_key, meta_key)

    async def update_note_meta(self, note_id: int, created_at: str, modified_at: str, last_read: str = None):
        key = RedisKeys.NOTE_META.format(id=note_id)
        mapping = {
            "created_at": created_at,
            "modified_at": modified_at
        }
        if last_read:
            mapping["last_read_at"] = last_read

        # hset принимает mapping в новых версиях redis-py
        await self.client.hset(key, mapping=mapping)

    async def get_note_meta(self, note_id: int) -> Optional[Dict[str, str]]:
        key = RedisKeys.NOTE_META.format(id=note_id)
        exists = await self.client.exists(key)
        if not exists:
            return None
        return await self.hash_get_all(key)

class RedisApiService:
    def __init__(self, redis_repo: RedisRepository):
        self.repo = redis_repo

    async def handle_string(self, key: str, value: str = None, op: str = "set", ttl: int = None):
        if op == "set":
            await self.repo.set_key(key, value, ex=ttl)
            return {"status": "ok"}
        elif op == "get":
            val = await self.repo.get_key(key)
            return {"value": val}
        elif op == "delete":
            await self.repo.delete_key(key)
            return {"status": "deleted"}
        elif op == "expire":
            await self.repo.expire_key(key, ttl)
            return {"status": "ttl_set"}
        elif op == "incr":
            val = await self.repo.incr_key(key)
            return {"value": val}
        raise HTTPException(400, "Invalid operation for string")

    async def handle_list(self, key: str, value: str = None, op: str = "push"):
        if op == "push":
            await self.repo.list_push(key, value)
            return {"status": "pushed"}
        elif op == "get":
            items = await self.repo.list_get(key)
            return {"items": items}
        elif op == "delete":
            await self.repo.delete_key(key)
            return {"status": "deleted"}
        raise HTTPException(400, "Invalid operation for list")

    async def handle_hash(self, key: str, field: str = None, value: str = None, op: str = "set", increment: int = None):
        if op == "set":
            await self.repo.hash_set(key, field, value)
            return {"status": "ok"}
        elif op == "get":
            data = await self.repo.hash_get_all(key)
            return {"data": data}
        elif op == "incr":
            if not field:
                raise HTTPException(400, "Field required for hash increment")
            val = await self.repo.hash_increment(key, field, increment or 1)
            return {"value": val}
        elif op == "delete":
            await self.repo.delete_key(key)
            return {"status": "deleted"}
        raise HTTPException(400, "Invalid operation for hash")


class NotesService:
    def __init__(self, db_repo: DatabaseRepository, redis_repo: RedisRepository):
        self.db_repo = db_repo
        self.redis_repo = redis_repo

    async def create_note(self, title: str, content: str) -> Dict:
        db_note = await self.db_repo.create_note(title, content)

        await self.redis_repo.cache_note_content(db_note.id, content)

        await self.redis_repo.update_note_meta(
            db_note.id,
            db_note.created_at.isoformat(),
            db_note.updated_at.isoformat()
        )

        return {"id": db_note.id, "title": db_note.title, "created_at": db_note.created_at.isoformat()}

    async def get_note_metadata(self, note_id: int) -> Dict:
        meta = await self.redis_repo.get_note_meta(note_id)

        if not meta:
            db_note = await self.db_repo.get_note(note_id)
            if not db_note:
                raise HTTPException(404, "Note not found")

            now = datetime.utcnow().isoformat()
            await self.redis_repo.update_note_meta(
                db_note.id,
                db_note.created_at.isoformat(),
                db_note.updated_at.isoformat(),
                now
            )
            await self.redis_repo.cache_note_content(db_note.id, db_note.content)

            meta = {
                "created_at": db_note.created_at.isoformat(),
                "modified_at": db_note.updated_at.isoformat(),
                "last_read_at": now
            }
        else:
            now = datetime.utcnow().isoformat()
            await self.redis_repo.hash_set(RedisKeys.NOTE_META.format(id=note_id), "last_read_at", now)
            meta['last_read_at'] = now

        return meta

    async def update_note(self, note_id: int, title: str, content: str) -> Dict:
        db_note = await self.db_repo.update_note(note_id, title, content)
        if not db_note:
            raise HTTPException(404, "Note not found")

        # Update Cache
        await self.redis_repo.cache_note_content(note_id, content)
        await self.redis_repo.update_note_meta(
            note_id,
            db_note.created_at.isoformat(),  # Created at doesn't change
            db_note.updated_at.isoformat()
        )
        return {"id": db_note.id, "status": "updated"}

    async def delete_note(self, note_id: int) -> Dict:
        success = await self.db_repo.delete_note(note_id)
        if not success:
            raise HTTPException(404, "Note not found")

        await self.redis_repo.delete_note_cache(note_id)
        return {"status": "deleted"}

class RedisController:
    @inject
    def __init__(self, service: RedisApiService = Provide["redis_api_service"]):
        self.service = service

    def register_routes(self, app: FastAPI):
        @app.post("/redis/string/{key}")
        async def string_op(key: str, value: str = Body(...), op: str = Body("set"), ttl: int = Body(None)):
            return await self.service.handle_string(key, value, op, ttl)

        @app.get("/redis/string/{key}")
        async def string_get(key: str):
            return await self.service.handle_string(key, op="get")

        @app.post("/redis/list/{key}")
        async def list_op(key: str, value: str = Body(...), op: str = Body("push")):
            return await self.service.handle_list(key, value, op)

        @app.get("/redis/list/{key}")
        async def list_get(key: str):
            return await self.service.handle_list(key, op="get")

        @app.post("/redis/hash/{key}")
        async def hash_op(key: str, field: str = Body(...), value: str = Body(...), op: str = Body("set"),
                          increment: int = Body(None)):
            return await self.service.handle_hash(key, field, value, op, increment)

        @app.get("/redis/hash/{key}")
        async def hash_get(key: str):
            return await self.service.handle_hash(key, op="get")


class NotesController:
    @inject
    def __init__(self, service: NotesService = Provide["notes_service"]):
        self.service = service

    def register_routes(self, app: FastAPI):
        @app.post("/notes/")
        async def create_note(title: str = Body(...), content: str = Body(...)):
            return await self.service.create_note(title, content)

        @app.get("/notes/{note_id}/meta")
        async def get_meta(note_id: int):
            return await self.service.get_note_metadata(note_id)

        @app.put("/notes/{note_id}")
        async def update_note(note_id: int, title: str = Body(...), content: str = Body(...)):
            return await self.service.update_note(note_id, title, content)

        @app.delete("/notes/{note_id}")
        async def delete_note(note_id: int):
            return await self.service.delete_note(note_id)

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    db_engine = providers.Resource(
        create_async_engine,
        url=settings.DB_URL,
        echo=False
    )

    db_session_factory = providers.Factory(
        async_sessionmaker,
        bind=db_engine,
        expire_on_commit=False
    )

    redis_client = providers.Resource(
        redis.from_url,
        url=settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False
    )

    db_repository = providers.Factory(
        DatabaseRepository,
        session_factory=db_session_factory
    )

    redis_repository = providers.Factory(
        RedisRepository,
        client=redis_client
    )

    redis_api_service = providers.Factory(
        RedisApiService,
        redis_repo=redis_repository
    )

    notes_service = providers.Factory(
        NotesService,
        db_repo=db_repository,
        redis_repo=redis_repository
    )

    redis_controller = providers.Factory(
        RedisController,
        service=redis_api_service
    )

    notes_controller = providers.Factory(
        NotesController,
        service=notes_service
    )

container = Container()

app = FastAPI(title=settings.APP_NAME)

@app.on_event("startup")
async def startup_event():
    await container.db_engine.init()
    await container.redis_client.init()
    # Создание таблиц БД
    async with container.db_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Application started")

@app.on_event("shutdown")
async def shutdown_event():
    await container.redis_client.shutdown()
    await container.db_engine.shutdown()
    logger.info("Application shutdown")

redis_ctrl = RedisController(service=container.redis_api_service())
notes_ctrl = NotesController(service=container.notes_service())

redis_ctrl.register_routes(app)
notes_ctrl.register_routes(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)