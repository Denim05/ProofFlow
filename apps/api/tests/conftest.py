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

    async def find_one(self, query: Dict[str, Any]):
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if isinstance(v, dict) and "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                return copy.deepcopy(doc)
        return None

    async def find_one_and_update(self, filter_query: Dict[str, Any], update_query: Dict[str, Any], return_document=False):
        for doc in self.documents:
            match = True
            for k, v in filter_query.items():
                if isinstance(v, dict) and "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
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
            match = True
            for k, v in filter_query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update_query:
                    doc.update(copy.deepcopy(update_query["$set"]))
                if "$inc" in update_query:
                    for inc_k, inc_v in update_query["$inc"].items():
                        doc[inc_k] = doc.get(inc_k, 0) + inc_v
                return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def delete_many(self, query: Dict[str, Any]):
        initial_len = len(self.documents)
        new_docs = []
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if isinstance(v, dict) and "$lt" in v:
                    if doc.get(k) < v["$lt"]:
                        continue
                    else:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if not match:
                new_docs.append(doc)
        self.documents = new_docs
        return type("DeleteResult", (), {"deleted_count": initial_len - len(new_docs)})()

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


@pytest_asyncio.fixture
async def client(fake_db):
    """Provides an HTTPX AsyncClient with the database dependency overridden with in-memory store."""
    app.dependency_overrides[get_db] = lambda: fake_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
