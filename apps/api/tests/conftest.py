import copy
from typing import Any, Dict, List
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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


class FakeAsyncCasesCollection:
    """In-memory asynchronous collection mimicking PyMongo AsyncCollection."""

    def __init__(self):
        self.documents: List[Dict[str, Any]] = []

    async def insert_one(self, doc: Dict[str, Any]):
        doc_copy = copy.deepcopy(doc)
        self.documents.append(doc_copy)
        return type("InsertResult", (), {"inserted_id": doc_copy.get("_id", "mock_id")})()

    async def find_one(self, query: Dict[str, Any]):
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return copy.deepcopy(doc)
        return None

    def find(self, query: Dict[str, Any]):
        matching = []
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                matching.append(copy.deepcopy(doc))
        return FakeAsyncCursor(matching)

    async def count_documents(self, query: Dict[str, Any]) -> int:
        count = 0
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count

    async def create_index(self, *args, **kwargs):
        return "idx_created"


class FakeAsyncDatabase:
    """In-memory database containing simulated collections."""

    def __init__(self):
        self.cases = FakeAsyncCasesCollection()


@pytest_asyncio.fixture
async def fake_db():
    return FakeAsyncDatabase()


@pytest_asyncio.fixture
async def client(fake_db):
    """Provides an HTTPX AsyncClient with the database dependency overridden with in-memory store."""
    app.dependency_overrides[get_db] = lambda: fake_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
