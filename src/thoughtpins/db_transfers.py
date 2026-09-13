"""Encrypted temporary bytes shared by API replicas and import workers."""

from sqlalchemy import Column, ForeignKey, Index, Integer, LargeBinary, String

from thoughtpins.db_base import Base, _new_id


class VaultImportChunk(Base):
    __tablename__ = "vault_import_chunks"
    __table_args__ = (Index("ix_vault_import_chunks_owner_offset", "user_id", "transfer_id", "offset", unique=True),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    transfer_id = Column(String(32), ForeignKey("vault_import_sessions.id", ondelete="CASCADE"), nullable=False)
    offset = Column(Integer, nullable=False)
    byte_size = Column(Integer, nullable=False)
    payload = Column(LargeBinary, nullable=False)
