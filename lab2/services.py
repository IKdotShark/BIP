from typing import Dict, Optional, Any, List
from datetime import datetime
from fastapi import HTTPException
from repositories import DatabaseRepository, RedisRepository, RedisKeys

# ==================== Redis API Service ====================
class RedisApiService:
    """Сервис для работы с Redis API"""

    def __init__(self, redis_repo: RedisRepository):
        self.repo = redis_repo

    async def handle_string(self, key: str, value: Optional[str] = None, op: str = "set", ttl: Optional[int] = None) -> \
    Dict[str, Any]:
        if op == "set":
            await self.repo.set_key(key, value, ex=ttl)
            return {"status": "ok"}
        elif op == "get":
            return {"value": await self.repo.get_key(key)}
        elif op == "delete":
            await self.repo.delete_key(key)
            return {"status": "deleted"}
        elif op == "expire":
            await self.repo.expire_key(key, ttl)
            return {"status": "ttl_set"}
        elif op == "incr":
            return {"value": await self.repo.incr_key(key)}
        raise HTTPException(400, f"Invalid operation: {op}")

    async def handle_list(self, key: str, value: Optional[str] = None, op: str = "push") -> Dict[str, Any]:
        if op == "push":
            await self.repo.list_push(key, value)
            return {"status": "pushed"}
        elif op == "get":
            return {"items": await self.repo.list_get(key)}
        elif op == "delete":
            await self.repo.delete_key(key)
            return {"status": "deleted"}
        raise HTTPException(400, f"Invalid operation: {op}")

    async def handle_hash(self, key: str, field: Optional[str] = None, value: Optional[str] = None, op: str = "set",
                          increment: Optional[int] = None) -> Dict[str, Any]:
        if op == "set":
            await self.repo.hash_set(key, field, value)
            return {"status": "ok"}
        elif op == "get":
            return {"data": await self.repo.hash_get_all(key)}
        elif op == "incr":
            return {"value": await self.repo.hash_increment(key, field, increment or 1)}
        elif op == "delete":
            await self.repo.delete_key(key)
            return {"status": "deleted"}
        raise HTTPException(400, f"Invalid operation: {op}")


# ==================== Notes Service ====================
class NotesService:
    """Сервис для работы с заметками"""

    def __init__(self, db_repo: DatabaseRepository, redis_repo: RedisRepository):
        self.db_repo = db_repo
        self.redis_repo = redis_repo

    async def create_note(self, title: str, content: str) -> Dict:
        db_note = await self.db_repo.create_note(title, content)
        await self.redis_repo.cache_note_content(db_note.id, content)
        await self.redis_repo.update_note_meta(db_note.id, db_note.created_at.isoformat(),
                                               db_note.updated_at.isoformat())
        return {"id": db_note.id, "title": db_note.title, "created_at": db_note.created_at.isoformat()}

    async def get_note_metadata(self, note_id: int) -> Dict:
        meta = await self.redis_repo.get_note_meta(note_id)

        if not meta:
            db_note = await self.db_repo.get_note(note_id)
            if not db_note:
                raise HTTPException(404, "Note not found")

            now = datetime.utcnow().isoformat()
            await self.redis_repo.update_note_meta(db_note.id, db_note.created_at.isoformat(),
                                                   db_note.updated_at.isoformat(), now)
            await self.redis_repo.cache_note_content(db_note.id, db_note.content)
            meta = {"created_at": db_note.created_at.isoformat(), "modified_at": db_note.updated_at.isoformat(),
                    "last_read_at": now}
        else:
            now = datetime.utcnow().isoformat()
            await self.redis_repo.hash_set(RedisKeys.NOTE_META.format(id=note_id), "last_read_at", now)
            meta["last_read_at"] = now

        return meta

    async def update_note(self, note_id: int, title: str, content: str) -> Dict:
        db_note = await self.db_repo.update_note(note_id, title, content)
        if not db_note:
            raise HTTPException(404, "Note not found")

        await self.redis_repo.cache_note_content(note_id, content)
        await self.redis_repo.update_note_meta(note_id, db_note.created_at.isoformat(), db_note.updated_at.isoformat())
        return {"id": db_note.id, "status": "updated"}

    async def delete_note(self, note_id: int) -> Dict:
        success = await self.db_repo.delete_note(note_id)
        if not success:
            raise HTTPException(404, "Note not found")

        await self.redis_repo.delete_note_cache(note_id)
        return {"status": "deleted"}