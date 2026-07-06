from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
from .user import gen_id


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("q"))
    asker_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[list] = mapped_column(JSONB, default=list)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_responders: Mapped[int] = mapped_column(Integer, default=5)
    matched_agent_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    fuel_cost: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String, default="open")  # open | closed | expired
    visibility: Mapped[str] = mapped_column(String, default="public")
    estimated_fuel_per_answer: Mapped[int] = mapped_column(BigInteger, default=900)
    base_cap_multiplier: Mapped[float] = mapped_column(Numeric(4, 2), default=1.5)
    base_fuel_reserved: Mapped[int] = mapped_column(BigInteger, default=0)
    base_fuel_spent: Mapped[int] = mapped_column(BigInteger, default=0)
    reward_fuel: Mapped[int] = mapped_column(BigInteger, default=0)
    reward_status: Mapped[str] = mapped_column(String, default="none")
    reward_answer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reward_awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reward_auto_award_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    root_question_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_question_id: Mapped[str | None] = mapped_column(String, nullable=True)
    quoted_answer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_type: Mapped[str] = mapped_column(String, default="root")  # root | followup
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
