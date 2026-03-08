import json
from datetime import datetime, timezone
from sqlalchemy import String, Float, Text, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DiscoverySession(Base):
    __tablename__ = "discovery_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="created")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    clarification_count: Mapped[int] = mapped_column(Integer, default=0)
    profile_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    known_facts: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def set_profile(self, profile: dict) -> None:
        self.profile_data = json.dumps(profile)

    def get_profile(self) -> dict | None:
        if self.profile_data:
            return json.loads(self.profile_data)
        return None

    def set_known_facts(self, facts: dict) -> None:
        self.known_facts = json.dumps(facts)

    def get_known_facts(self) -> dict:
        return json.loads(self.known_facts) if self.known_facts else {}


class PersonProfileRecord(Base):
    __tablename__ = "person_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    profile_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def get_profile(self) -> dict:
        return json.loads(self.profile_data)


class SearchCacheEntry(Base):
    __tablename__ = "search_cache"
    __table_args__ = (
        Index("ix_cache_lookup", "query_hash", "search_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_type: Mapped[str] = mapped_column(String(20), nullable=False)
    results_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def get_results(self) -> list[dict]:
        return json.loads(self.results_data)

    def set_results(self, results: list[dict]) -> None:
        self.results_data = json.dumps(results)

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now > exp
