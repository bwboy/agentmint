from datetime import datetime, date
from sqlalchemy import String, Integer, BigInteger, Numeric, DateTime, Date, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
from .user import gen_id


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("a"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    agent_type: Mapped[str] = mapped_column(String, nullable=False)  # openclaw | hermes
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    visibility: Mapped[str] = mapped_column(String, default="public")
    service_mode: Mapped[str] = mapped_column(String, default="auto_match")
    service_rules: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {
            "price_multiplier": 1.0,
            "max_followup_depth": 2,
            "min_fuel_per_answer": 0,
            "max_fuel_per_answer": 100000,
            "max_questions_per_user_per_day": 20,
            "max_fuel_per_day": 1000000,
        },
    )
    status: Mapped[str] = mapped_column(String, default="offline")  # online | offline | paused
    repute_score: Mapped[float] = mapped_column(Numeric(3, 1), default=0)
    fuel_earned: Mapped[int] = mapped_column(BigInteger, default=0)
    total_answers: Mapped[int] = mapped_column(Integer, default=0)
    approval_rate: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_quota_config: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {"max": 50, "auto_threshold": 40, "emergency_reserve": 3}
    )
    review_rules: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {"auto_trust_level": 2, "auto_tag_match": True}
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("conn"))
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    last_ip: Mapped[str] = mapped_column(String, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AgentDailyUsage(Base):
    __tablename__ = "agent_daily_usage"

    agent_id: Mapped[str] = mapped_column(
        String, ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
