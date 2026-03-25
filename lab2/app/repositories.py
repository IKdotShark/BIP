from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import redis.asyncio as redis

from models import NoteDBModel, RedisKeys

# ==================== Database Repository ====================
class DatabaseRepository:
    """Репозиторий для работы с БД"""

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
            return await session.get(NoteDBModel, note_id)

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


# ==================== Redis Repository ====================
class RedisRepository:
    """Репозиторий для работы с Redis"""

    def __init__(self, client: redis.Redis):
        self.client = client

    # --- Generic Operations ---
    async def set_key(self, key: str, value: str, ex: Optional[int] = None):
        await self.client.set(key, value, ex=ex)

    async def get_key(self, key: str) -> Optional[str]:
        value = await self.client.get(key)
        return value.decode() if value else None

    async def delete_key(self, key: str):
        await self.client.delete(key)

    async def expire_key(self, key: str, seconds: int):
        await self.client.expire(key, seconds)

    async def incr_key(self, key: str) -> int:
        return await self.client.incr(key)

    # --- List Operations ---
    async def list_push(self, key: str, value: str):
        await self.client.lpush(key, value)

    async def list_get(self, key: str) -> List[str]:
        items = await self.client.lrange(key, 0, -1)
        return [item.decode() for item in items]

    # --- Hash Operations ---
    async def hash_set(self, key: str, field: str, value: str):
        await self.client.hset(key, field, value)

    async def hash_get_all(self, key: str) -> Dict[str, str]:
        data = await self.client.hgetall(key)
        return {k.decode(): v.decode() for k, v in data.items()}

    async def hash_increment(self, key: str, field: str, amount: int = 1) -> int:
        return await self.client.hincrby(key, field, amount)

    # --- Notes Cache ---
    async def cache_note_content(self, note_id: int, content: str):
        key = RedisKeys.NOTE_CONTENT.format(id=note_id)
        await self.client.set(key, content)

    async def get_cached_note_content(self, note_id: int) -> Optional[str]:
        key = RedisKeys.NOTE_CONTENT.format(id=note_id)
        value = await self.client.get(key)
        return value.decode() if value else None

    async def delete_note_cache(self, note_id: int):
        content_key = RedisKeys.NOTE_CONTENT.format(id=note_id)
        meta_key = RedisKeys.NOTE_META.format(id=note_id)
        await self.client.delete(content_key, meta_key)

    async def update_note_meta(self, note_id: int, created_at: str, modified_at: str, last_read: Optional[str] = None):
        key = RedisKeys.NOTE_META.format(id=note_id)
        mapping = {"created_at": created_at, "modified_at": modified_at}
        if last_read:
            mapping["last_read_at"] = last_read
        await self.client.hset(key, mapping=mapping)

    async def get_note_meta(self, note_id: int) -> Optional[Dict[str, str]]:
        key = RedisKeys.NOTE_META.format(id=note_id)
        exists = await self.client.exists(key)
        if not exists:
            return None
        return await self.hash_get_all(key)