"""Tests for person deduplication and smart merge logic."""
import json
import uuid

import pytest
from sqlalchemy import select

from app.api.routes import (
    _normalize_name,
    _names_match,
    _companies_match,
    _merge_scalar,
    _merge_list_field,
    _merge_dict_field,
    _find_existing_person,
)


class TestNormalizeName:
    def test_basic(self):
        assert _normalize_name("John Doe") == "john doe"

    def test_strips_punctuation(self):
        assert _normalize_name("Dr. Jane O'Brien") == "dr jane obrien"

    def test_strips_whitespace(self):
        assert _normalize_name("  Sam  Altman  ") == "sam  altman"

    def test_empty(self):
        assert _normalize_name("") == ""


class TestNamesMatch:
    def test_exact_match(self):
        assert _names_match("Sam Altman", "Sam Altman") is True

    def test_case_insensitive(self):
        assert _names_match("sam altman", "SAM ALTMAN") is True

    def test_different_names(self):
        assert _names_match("Sam Altman", "Jensen Huang") is False

    def test_reordered_parts(self):
        assert _names_match("Altman Sam", "Sam Altman") is True

    def test_single_name_no_match(self):
        assert _names_match("Sam", "Samuel") is False

    def test_empty_string(self):
        assert _names_match("", "Sam") is False
        assert _names_match("Sam", "") is False


class TestCompaniesMatch:
    def test_exact(self):
        assert _companies_match("OpenAI", "OpenAI") is True

    def test_case_insensitive(self):
        assert _companies_match("openai", "OPENAI") is True

    def test_with_suffix(self):
        assert _companies_match("Microsoft Corp", "Microsoft") is True
        assert _companies_match("Apple Inc.", "Apple") is True

    def test_both_none(self):
        assert _companies_match(None, None) is True

    def test_one_none(self):
        assert _companies_match("OpenAI", None) is False
        assert _companies_match(None, "OpenAI") is False

    def test_different(self):
        assert _companies_match("OpenAI", "Google") is False


class TestMergeScalar:
    def test_new_wins_when_longer(self):
        assert _merge_scalar("short bio", "a much longer and detailed bio") == "a much longer and detailed bio"

    def test_old_wins_when_longer(self):
        assert _merge_scalar("a much longer existing bio", "short") == "a much longer existing bio"

    def test_new_replaces_none(self):
        assert _merge_scalar(None, "new value") == "new value"

    def test_old_preserved_when_new_none(self):
        assert _merge_scalar("old value", None) == "old value"

    def test_both_none(self):
        assert _merge_scalar(None, None) is None


class TestMergeListField:
    def test_union_strings(self):
        result = _merge_list_field(["AI", "ML"], ["ML", "NLP"])
        assert "AI" in result
        assert "ML" in result
        assert "NLP" in result
        assert len(result) == 3

    def test_case_insensitive_dedup(self):
        result = _merge_list_field(["Python"], ["python"])
        assert len(result) == 1

    def test_dict_items(self):
        old = [{"role": "CEO", "company": "OpenAI"}]
        new = [{"role": "CEO", "company": "OpenAI"}, {"role": "President", "company": "YC"}]
        result = _merge_list_field(old, new)
        assert len(result) == 2

    def test_none_inputs(self):
        assert _merge_list_field(None, ["a"]) == ["a"]
        assert _merge_list_field(["a"], None) == ["a"]
        assert _merge_list_field(None, None) == []


class TestMergeDictField:
    def test_merge_non_null(self):
        old = {"linkedin": "https://linkedin.com/in/old", "twitter": "https://twitter.com/x"}
        new = {"linkedin": "https://linkedin.com/in/new", "github": "https://github.com/user"}
        result = _merge_dict_field(old, new)
        assert result["linkedin"] == "https://linkedin.com/in/new"
        assert result["twitter"] == "https://twitter.com/x"
        assert result["github"] == "https://github.com/user"

    def test_null_in_new_preserved_old(self):
        old = {"linkedin": "https://linkedin.com/in/old"}
        new = {"linkedin": None}
        result = _merge_dict_field(old, new)
        assert result["linkedin"] == "https://linkedin.com/in/old"

    def test_none_inputs(self):
        assert _merge_dict_field(None, {"a": 1}) == {"a": 1}
        assert _merge_dict_field({"a": 1}, None) == {"a": 1}
        assert _merge_dict_field(None, None) == {}


@pytest.mark.asyncio
async def test_find_existing_person_exact_match(db_session):
    """Should find person by exact name match."""
    from app.models.db_models import Person
    from app.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        person = Person(
            id=str(uuid.uuid4()),
            name="Sam Altman",
            company="OpenAI",
            bio="CEO of OpenAI",
            confidence_score=0.95,
        )
        session.add(person)
        await session.commit()
        person_id = person.id

    async with factory() as session:
        found = await _find_existing_person(session, "Sam Altman", "OpenAI")
        assert found is not None
        assert found.id == person_id


@pytest.mark.asyncio
async def test_find_existing_person_case_insensitive(db_session):
    """Should match regardless of case."""
    from app.models.db_models import Person
    from app.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        person = Person(
            id=str(uuid.uuid4()),
            name="Jensen Huang",
            company="NVIDIA",
            confidence_score=0.9,
        )
        session.add(person)
        await session.commit()
        person_id = person.id

    async with factory() as session:
        found = await _find_existing_person(session, "jensen huang", "NVIDIA Corporation")
        assert found is not None
        assert found.id == person_id


@pytest.mark.asyncio
async def test_find_existing_person_no_match(db_session):
    """Should return None when no match."""
    from app.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        found = await _find_existing_person(session, "Nobody Special", "NoCompany")
        assert found is None


@pytest.mark.asyncio
async def test_merge_preserves_old_sources(client, db_session):
    """When a person is rediscovered, old sources must not be lost."""
    from app.models.db_models import Person, PersonSource
    from app.db import get_session_factory

    pid = str(uuid.uuid4())
    factory = get_session_factory()
    async with factory() as session:
        person = Person(
            id=pid,
            name="Merge Test",
            company="TestCo",
            bio="Original bio",
            confidence_score=0.7,
            version=1,
        )
        person.set_json("expertise", ["Python", "AI"])
        person.set_json("social_links", {"linkedin": "https://li.com/old"})
        session.add(person)
        await session.flush()

        old_source = PersonSource(
            person_id=pid,
            source_type="web",
            platform="web",
            url="https://old-source.com/page",
            title="Old Source",
            relevance_score=0.8,
        )
        session.add(old_source)
        await session.commit()

    async with factory() as session:
        person = (await session.execute(
            select(Person).where(Person.id == pid)
        )).scalar_one()

        sources = (await session.execute(
            select(PersonSource).where(PersonSource.person_id == pid)
        )).scalars().all()
        assert len(sources) == 1
        assert sources[0].url == "https://old-source.com/page"
        assert person.get_json("expertise") == ["Python", "AI"]
