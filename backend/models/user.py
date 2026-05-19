import uuid
from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("u"))
    phone: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String, nullable=False)
    trust_level: Mapped[int] = mapped_column(Integer, default=1)
    fuel_balance: Mapped[int] = mapped_column(BigInteger, default=50000)
    repute_score: Mapped[float] = mapped_column(Numeric(3, 1), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
