from fastapi import APIRouter, Body
from typing import Optional

from services import RedisApiService, NotesService


# ==================== Redis Controller ====================
class RedisController:
    """Контроллер для Redis API"""

    def __init__(self, service: RedisApiService):
        self.service = service
        self.router = APIRouter(prefix="/redis", tags=["Redis"])
        self._register_routes()

    def _register_routes(self):
        @self.router.post("/string/{key}")
        async def string_op(key: str, value: Optional[str] = Body(None), op: str = Body("set"),
                            ttl: Optional[int] = Body(None)):
            return await self.service.handle_string(key, value, op, ttl)

        @self.router.get("/string/{key}")
        async def string_get(key: str):
            return await self.service.handle_string(key, op="get")

        @self.router.post("/list/{key}")
        async def list_op(key: str, value: Optional[str] = Body(None), op: str = Body("push")):
            return await self.service.handle_list(key, value, op)

        @self.router.get("/list/{key}")
        async def list_get(key: str):
            return await self.service.handle_list(key, op="get")

        @self.router.post("/hash/{key}")
        async def hash_op(key: str, field: Optional[str] = Body(None), value: Optional[str] = Body(None),
                          op: str = Body("set"), increment: Optional[int] = Body(None)):
            return await self.service.handle_hash(key, field, value, op, increment)

        @self.router.get("/hash/{key}")
        async def hash_get(key: str):
            return await self.service.handle_hash(key, op="get")


# ==================== Notes Controller ====================
class NotesController:
    """Контроллер для заметок"""

    def __init__(self, service: NotesService):
        self.service = service
        self.router = APIRouter(prefix="/notes", tags=["Notes"])
        self._register_routes()

    def _register_routes(self):
        @self.router.post("/")
        async def create_note(title: str = Body(...), content: str = Body(...)):
            return await self.service.create_note(title, content)

        @self.router.get("/{note_id}/meta")
        async def get_meta(note_id: int):
            return await self.service.get_note_metadata(note_id)

        @self.router.put("/{note_id}")
        async def update_note(note_id: int, title: str = Body(...), content: str = Body(...)):
            return await self.service.update_note(note_id, title, content)

        @self.router.delete("/{note_id}")
        async def delete_note(note_id: int):
            return await self.service.delete_note(note_id)