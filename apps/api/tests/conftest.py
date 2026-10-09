import copy
from typing import Any, Dict, List, Optional
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.core.dependencies import get_db
from app.main import app


class FakeAsyncCursor:
    """Simulates an asynchronous PyMongo cursor with chaining."""

    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs
        self._index = 0

    def sort(self, key_or_list, direction=None):
        self._docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return self

    def skip(self, n: int):
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index < len(self._docs):
            doc = self._docs[self._index]
            self._index += 1
            return doc
        raise StopAsyncIteration


class FakeAsyncCollection:
    """In-memory asynchronous collection mimicking PyMongo AsyncCollection."""

    def __init__(self):
        self.documents: List[Dict[str, Any]] = []

    async def insert_one(self, doc: Dict[str, Any]):
        doc_copy = copy.deepcopy(doc)
        self.documents.append(doc_copy)
        return type("InsertResult", (), {"inserted_id": doc_copy.get("_id", "mock_id")})()

    async def insert_many(self, docs: List[Dict[str, Any]]):
        for doc in docs:
            self.documents.append(copy.deepcopy(doc))
        return type("InsertManyResult", (), {"inserted_ids": [d.get("_id", "mock_id") for d in docs]})()

    @staticmethod
    def _matches_condition(doc: Dict[str, Any], k: str, v: Any) -> bool:
        if k == "$or" and isinstance(v, list):
            return any(FakeAsyncCollection._matches(doc, cond) for cond in v)
        if isinstance(v, dict):
            if "$in" in v:
                return doc.get(k) in v["$in"]
            if "$lt" in v:
                val = doc.get(k)
                return val is not None and val < v["$lt"]
            if "$ne" in v:
                return doc.get(k) != v["$ne"]
        return doc.get(k) == v

    @classmethod
    def _matches(cls, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        for k, v in query.items():
            if not cls._matches_condition(doc, k, v):
                return False
        return True

    async def find_one(self, query: Dict[str, Any]):
        for doc in self.documents:
            if self._matches(doc, query):
                return copy.deepcopy(doc)
        return None

    async def find_one_and_update(self, filter_query: Dict[str, Any], update_query: Dict[str, Any], return_document=False):
        for doc in self.documents:
            if self._matches(doc, filter_query):
                old_doc = copy.deepcopy(doc)
                if "$set" in update_query:
                    doc.update(copy.deepcopy(update_query["$set"]))
                if "$inc" in update_query:
                    for inc_k, inc_v in update_query["$inc"].items():
                        doc[inc_k] = doc.get(inc_k, 0) + inc_v
                return copy.deepcopy(doc if return_document else old_doc)
        return None

    async def update_one(self, filter_query: Dict[str, Any], update_query: Dict[str, Any]):
        for doc in self.documents:
            if self._matches(doc, filter_query):
                if "$set" in update_query:
                    doc.update(copy.deepcopy(update_query["$set"]))
                if "$inc" in update_query:
                    for inc_k, inc_v in update_query["$inc"].items():
                        doc[inc_k] = doc.get(inc_k, 0) + inc_v
                return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def update_many(self, filter_query: Dict[str, Any], update_query: Dict[str, Any]):
        modified_count = 0
        for doc in self.documents:
            if self._matches(doc, filter_query):
                if "$set" in update_query:
                    doc.update(copy.deepcopy(update_query["$set"]))
                if "$inc" in update_query:
                    for inc_k, inc_v in update_query["$inc"].items():
                        doc[inc_k] = doc.get(inc_k, 0) + inc_v
                modified_count += 1
        return type("UpdateResult", (), {"modified_count": modified_count})()

    async def delete_many(self, query: Dict[str, Any]):
        initial_len = len(self.documents)
        new_docs = [doc for doc in self.documents if not self._matches(doc, query)]
        self.documents = new_docs
        return type("DeleteResult", (), {"deleted_count": initial_len - len(new_docs)})()

    def find(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None):
        matching = []
        for doc in self.documents:
            if self._matches(doc, query):
                if projection:
                    projected = {k: v for k, v in doc.items() if projection.get(k)}
                    matching.append(copy.deepcopy(projected))
                else:
                    matching.append(copy.deepcopy(doc))
        return FakeAsyncCursor(matching)

    async def count_documents(self, query: Dict[str, Any]) -> int:
        return sum(1 for doc in self.documents if self._matches(doc, query))

    async def create_index(self, *args, **kwargs):
        return "idx_created"


FakeAsyncCasesCollection = FakeAsyncCollection


class FakeAsyncDatabase:
    """In-memory database containing simulated collections."""

    def __init__(self):
        self.cases = FakeAsyncCollection()
        self.evidence = FakeAsyncCollection()
        self.events = FakeAsyncCollection()


@pytest_asyncio.fixture
async def fake_db():
    return FakeAsyncDatabase()


@pytest_asyncio.fixture(autouse=True)
def setup_test_auth_bypass():
    """Automatically enables dev auth bypass for test suite unless overridden by a test."""
    orig_bypass = settings.ALLOW_DEV_AUTH_BYPASS
    settings.ALLOW_DEV_AUTH_BYPASS = True
    yield
    settings.ALLOW_DEV_AUTH_BYPASS = orig_bypass


@pytest_asyncio.fixture
async def client(fake_db):
    """Provides an HTTPX AsyncClient with the database dependency overridden with in-memory store."""
    app.dependency_overrides[get_db] = lambda: fake_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
