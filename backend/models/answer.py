from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
from .user import gen_id


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("ans"))
    question_id: Mapped[str] = mapped_column(String, ForeignKey("questions.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    model: Mapped[str] = mapped_column(String, default="")
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    capability: Mapped[dict] = mapped_column(JSONB, default=dict)
    # State: assigned → pushed → processing → draft → approved/rejected/expired
    status: Mapped[str] = mapped_column(String, default="assigned")
    review_method: Mapped[str] = mapped_column(String, default="auto")
    fuel_earned: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(Base):
    __tablename__ = "feedbacks"
    __table_args__ = (UniqueConstraint("answer_id", "voter_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("fb"))
    answer_id: Mapped[str] = mapped_column(String, ForeignKey("answers.id"), nullable=False)
    voter_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    vote: Mapped[str] = mapped_column(String, nullable=False)  # up | down
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
