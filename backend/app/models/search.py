from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    query: str
    search_type: str = Field(description="web, linkedin, youtube, news, academic")
    rationale: str = Field(description="Why this query helps identify the person")


class SearchResult(BaseModel):
    title: str
    url: str
    content: str
    source_type: str
    score: float = Field(ge=0, le=1, default=0.5)


class SearchPlan(BaseModel):
    queries: list[SearchQuery]
    reasoning: str = Field(description="Strategy explanation for these queries")
