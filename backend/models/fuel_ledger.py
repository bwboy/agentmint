from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
from .user import gen_id


class FuelLedgerEntry(Base):
    __tablename__ = "fuel_ledger_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("fuel"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # debit | credit
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    question_id: Mapped[str | None] = mapped_column(String, nullable=True)
    answer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
