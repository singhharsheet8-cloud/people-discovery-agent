from pydantic import BaseModel, Field
from typing import Optional


class PersonSource(BaseModel):
    title: str
    url: str
    platform: str = Field(description="e.g. linkedin, youtube, news, blog, academic")
    snippet: str
    relevance_score: float = Field(ge=0, le=1)


class PersonProfile(BaseModel):
    name: str
    confidence_score: float = Field(ge=0, le=1)
    current_role: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    linkedin_url: Optional[str] = None
    key_facts: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    expertise: list[str] = Field(default_factory=list)
    notable_work: list[str] = Field(default_factory=list)
    social_links: dict[str, str] = Field(default_factory=dict)
    sources: list[PersonSource] = Field(default_factory=list)


class ClarificationRequest(BaseModel):
    question: str
    suggestions: list[str] = Field(default_factory=list)
    reason: str = Field(description="Why we need this clarification")
