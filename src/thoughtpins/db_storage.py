"""Original user uploads, encrypted independently for each owner."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String

from thoughtpins.db_base import Base, _new_id, _utcnow


class StoredAttachment(Base):
    __tablename__ = "stored_attachments"

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    reference = Column(String(255), nullable=False, unique=True)
    original_filename = Column(String(100), nullable=False)
    byte_size = Column(Integer, nullable=False)
    payload = Column(LargeBinary, nullable=False)
    created_at_utc = Column(DateTime, nullable=False, default=_utcnow)
