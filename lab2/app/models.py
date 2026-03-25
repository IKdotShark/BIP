from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

# ==================== Database Models ====================
Base = declarative_base()


class NoteDBModel(Base):
    """Модель заметки в БД"""

    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==================== Redis Keys ====================
class RedisKeys:
    """Шаблоны ключей Redis"""

    NOTE_CONTENT = "note:content:{id}"
    NOTE_META = "note:meta:{id}"