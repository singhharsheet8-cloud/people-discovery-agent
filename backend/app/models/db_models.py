import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, Float, Text, DateTime, Integer, Index, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.db import Base


# ── Known legal/birth name → canonical name mapping ──────────────────────────
# Used when computing name_key to collapse aliases to one canonical form.
_CANONICAL_NAMES: dict[str, str] = {
    "pichai sundararajan": "sundar pichai",
    "sundararajan pichai": "sundar pichai",
    "jen hsun huang":      "jensen huang",
    "jenhsun huang":       "jensen huang",
    "elon reeve musk":     "elon musk",
    "satya narayana nadella": "satya nadella",
    "timothy donald cook": "tim cook",
    "tim donald cook":     "tim cook",
}


def compute_name_key(name: str) -> str:
    """
    Produce a stable, normalised key for a person's name.

    Rules applied in order:
      1. Lowercase
      2. Replace hyphens / en-dashes with space
      3. Strip punctuation and accents (keep only a-z and spaces)
      4. Collapse whitespace
      5. Map known aliases to their canonical form
      6. Sort words alphabetically so "pichai sundar" == "sundar pichai"
      7. Take only first + last word (drop middle names) when ≥ 3 words

    The resulting key is stored in the DB and used for unique enforcement.
    """
    if not name:
        return ""
    s = name.lower()
    s = s.replace("‑", " ").replace("-", " ").replace(".", " ")
    s = re.sub(r"[^a-z\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Apply alias mapping (full-name lookup first)
    if s in _CANONICAL_NAMES:
        s = _CANONICAL_NAMES[s]

    words = s.split()
    if not words:
        return ""

    # Drop middle names: keep first + last only when 3+ words
    if len(words) >= 3:
        words = [words[0], words[-1]]

    # Sort alphabetically so word order doesn't matter
    words.sort()
    return " ".join(words)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = (
        # One row per canonical name. Enforced at the DB level by a UNIQUE
        # constraint AND a BEFORE INSERT/UPDATE trigger that calls
        # compute_name_key().  The Python model also sets it via __init__
        # so in-memory objects are always consistent.
        UniqueConstraint("name_key", name="uq_persons_name_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), index=True)
    # Canonical dedup key — auto-set by DB trigger; also set in Python __init__.
    name_key: Mapped[str] = mapped_column(String(255), index=True, nullable=True)
    current_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    key_facts: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    social_links: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    expertise: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    notable_work: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    career_timeline: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of skill strings
    projects: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of project dicts
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of recommendation dicts
    followers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blog_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    reputation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 1536-dim vector from text-embedding-3-small; null until first embedding run
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="discovered")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure name_key is always consistent with name at construction time.
        # The DB trigger handles it for raw SQL; this handles SQLAlchemy ORM paths.
        if self.name and not self.name_key:
            self.name_key = compute_name_key(self.name)

    _json_fields = ("education", "key_facts", "social_links", "expertise", "notable_work", "career_timeline",
                    "skills", "projects", "recommendations")

    def set_json(self, field: str, value: Any) -> None:
        if field not in self._json_fields:
            raise ValueError(f"Unknown JSON field: {field}")
        setattr(self, field, json.dumps(value) if value is not None else None)

    def get_json(self, field: str) -> Any:
        if field not in self._json_fields:
            raise ValueError(f"Unknown JSON field: {field}")
        val = getattr(self, field)
        if not val:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            import logging
            logging.getLogger(__name__).warning(
                "get_json: corrupted JSON in field '%s' for person %s — returning None",
                field, getattr(self, "id", "?"),
            )
            return None


class PersonSource(Base):
    __tablename__ = "person_sources"
    __table_args__ = (Index("ix_person_source_platform", "person_id", "platform"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("persons.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(50))
    platform: Mapped[str] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    source_reliability: Mapped[float] = mapped_column(Float, default=0.5)
    scorer_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SearchCache(Base):
    __tablename__ = "search_cache"
    __table_args__ = (Index("ix_search_cache_key_tool", "cache_key", "source_tool"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    source_tool: Mapped[str] = mapped_column(String(50))
    response_data: Mapped[str] = mapped_column(Text)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now > exp

    def get_results(self) -> list[dict]:
        if not self.response_data:
            return []
        try:
            return json.loads(self.response_data)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_results(self, results: list[dict]) -> None:
        self.response_data = json.dumps(results)


class DiscoveryJob(Base):
    __tablename__ = "discovery_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    person_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("persons.id"), nullable=True, index=True)
    input_params: Mapped[str] = mapped_column(Text)  # JSON
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    cost_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    sources_hit: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PersonVersion(Base):
    __tablename__ = "person_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("persons.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    profile_snapshot: Mapped[str] = mapped_column(Text)  # JSON
    diff_from_previous: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    trigger: Mapped[str] = mapped_column(String(50))  # e.g. "initial", "re-search", "manual_edit"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    events: Mapped[str] = mapped_column(Text, default='["job.completed"]')  # JSON list
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    endpoint_id: Mapped[str] = mapped_column(String(36), ForeignKey("webhook_endpoints.id"), index=True)
    event: Mapped[str] = mapped_column(String(50))
    payload: Mapped[str] = mapped_column(Text)  # JSON
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    rate_limit_per_day: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[str] = mapped_column(String(36), ForeignKey("api_keys.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(100))
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SavedList(Base):
    __tablename__ = "saved_lists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(20), default="#3b82f6")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class PersonListItem(Base):
    __tablename__ = "person_list_items"
    __table_args__ = (Index("ix_person_list_unique", "list_id", "person_id", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[str] = mapped_column(String(36), ForeignKey("saved_lists.id"), index=True)
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("persons.id"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PersonNote(Base):
    __tablename__ = "person_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("persons.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class PersonTag(Base):
    __tablename__ = "person_tags"
    __table_args__ = (Index("ix_person_tag_unique", "person_id", "tag", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("persons.id"), index=True)
    tag: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PublicShare(Base):
    __tablename__ = "public_shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("persons.id"), index=True)
    share_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
