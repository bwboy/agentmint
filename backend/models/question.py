from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
from .user import gen_id


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("q"))
    asker_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_responders: Mapped[int] = mapped_column(Integer, default=5)
    matched_agent_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    fuel_cost: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String, default="open")  # open | closed | expired
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
