import uuid
from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, Numeric, DateTime, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    avatar_url: Mapped[str] = mapped_column(String, default="")
    headline: Mapped[str] = mapped_column(String, default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    profile_tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    experience_tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    links: Mapped[dict] = mapped_column(JSONB, default=dict)
    profile_visibility: Mapped[str] = mapped_column(String, default="public")
    default_agent_visibility: Mapped[str] = mapped_column(String, default="public")
    default_agent_service_mode: Mapped[str] = mapped_column(String, default="auto_match")
    default_agent_service_rules: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {
            "price_multiplier": 1.0,
            "max_followup_depth": 2,
            "min_fuel_per_answer": 0,
            "max_fuel_per_answer": 100000,
        },
    )
    notification_prefs: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {
            "friend_request": True,
            "agent_subscribed": True,
            "direct_question": True,
            "answer_feedback": True,
        },
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
