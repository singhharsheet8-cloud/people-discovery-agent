from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    title: str
    url: str
    content: str
    source_type: str
    score: float = Field(ge=0, le=1, default=0.5)
