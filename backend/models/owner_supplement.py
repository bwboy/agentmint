from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from .user import gen_id


class AnswerOwnerSupplement(Base):
    __tablename__ = "answer_owner_supplements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("os"))
    question_id: Mapped[str] = mapped_column(String, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    answer_id: Mapped[str] = mapped_column(String, ForeignKey("answers.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    requester_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="")
    response: Mapped[str] = mapped_column(Text, default="")
    supplement_type: Mapped[str] = mapped_column(String, default="experience")
    status: Mapped[str] = mapped_column(String, default="pending")
    is_high_value: Mapped[bool] = mapped_column(Boolean, default=False)
    asker_reaction: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
