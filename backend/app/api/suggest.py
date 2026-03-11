import logging
from fastapi import APIRouter, Query
from sqlalchemy import select
from app.db import get_session_factory
from app.models.db_models import Person

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/suggest", tags=["suggest"])


@router.get("")
async def suggest(
    q: str = Query(..., min_length=1, max_length=100),
    type: str = Query("person", pattern="^(person|company)$"),
    limit: int = Query(5, ge=1, le=20),
):
    """Typeahead suggestions for person names or company names."""
    factory = get_session_factory()
    safe_q = q.replace("%", r"\%").replace("_", r"\_")

    async with factory() as session:
        if type == "person":
            stmt = (
                select(Person.id, Person.name, Person.company)
                .where(Person.name.ilike(f"%{safe_q}%"))
                .order_by(Person.updated_at.desc())
                .limit(limit)
            )
        else:
            stmt = (
                select(Person.company)
                .where(Person.company.ilike(f"%{safe_q}%"))
                .where(Person.company.isnot(None))
                .distinct()
                .limit(limit)
            )

        result = await session.execute(stmt)
        rows = result.all()

        if type == "person":
            return [{"id": r[0], "name": r[1], "company": r[2]} for r in rows]
        else:
            return [{"company": r[0]} for r in rows]
