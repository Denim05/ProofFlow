from typing import Any, Dict, Optional
import pymongo
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.core.logging import logger

_client: Optional[AsyncMongoClient] = None
_db: Optional[AsyncDatabase] = None


async def connect_to_mongo() -> None:
    """Initializes the MongoDB AsyncMongoClient connection pool and pings the server.

    Does not print or log connection URIs or credentials.
    """
    global _client, _db
    try:
        logger.info("Initializing MongoDB client...")
        _client = AsyncMongoClient(
            settings.MONGODB_URI,
            maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
            minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
            serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
        )
        # Perform live ping to verify connectivity
        await _client.admin.command("ping")
        _db = _client[settings.MONGODB_DATABASE]
        logger.info(
            "MongoDB connection established successfully for database: %s",
            settings.MONGODB_DATABASE,
        )
        await init_db_indexes(_db)
    except Exception as exc:
        logger.warning(
            "MongoDB ping unsuccessful during startup (database is disconnected): %s",
            str(exc),
        )
        # We retain client so check_db_health can attempt live recovery or report status
        if _client:
            _db = _client[settings.MONGODB_DATABASE]


async def close_mongo_connection() -> None:
    """Gracefully closes MongoDB connection pool."""
    global _client, _db
    if _client is not None:
        logger.info("Closing MongoDB AsyncMongoClient connection pool...")
        await _client.close()
        _client = None
        _db = None
        logger.info("MongoDB client closed successfully.")


def get_client() -> Optional[AsyncMongoClient]:
    """Returns the singleton AsyncMongoClient instance."""
    return _client


def get_database() -> Optional[AsyncDatabase]:
    """Returns the active AsyncDatabase instance."""
    return _db


async def check_db_health() -> Dict[str, str]:
    """Performs a real async ping against MongoDB to verify live connectivity.

    Returns:
        Dict with status ('healthy' or 'degraded') and database ('connected' or 'disconnected').
    """
    if _client is None:
        return {"status": "degraded", "database": "disconnected"}
    try:
        await _client.admin.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception:
        return {"status": "degraded", "database": "disconnected"}


async def init_db_indexes(db: Optional[AsyncDatabase] = None) -> None:
    """Prepares and verifies database indexes for approved Day 1 / Phase 1 collections.

    Only creates the approved indexes:
    1. cases: unique case_id
    2. cases: user_id + created_at
    3. cases: user_id + status + created_at
    """
    target_db = db if db is not None else _db
    if target_db is None:
        return

    try:
        # Index 1: Unique case_id
        await target_db.cases.create_index(
            [("case_id", pymongo.ASCENDING)],
            unique=True,
            name="idx_cases_case_id_unique",
        )

        # Index 2: Compound user_id + created_at (descending)
        await target_db.cases.create_index(
            [("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
            name="idx_cases_user_created",
        )

        # Index 3: Compound user_id + status + created_at (descending)
        await target_db.cases.create_index(
            [
                ("user_id", pymongo.ASCENDING),
                ("status", pymongo.ASCENDING),
                ("created_at", pymongo.DESCENDING),
            ],
            name="idx_cases_user_status_created",
        )

        # Evidence Collection Indexes
        await target_db.evidence.create_index(
            [("evidence_id", pymongo.ASCENDING)],
            unique=True,
            name="idx_evidence_evidence_id_unique",
        )
        await target_db.evidence.create_index(
            [
                ("user_id", pymongo.ASCENDING),
                ("case_id", pymongo.ASCENDING),
                ("created_at", pymongo.DESCENDING),
            ],
            name="idx_evidence_user_case_created",
        )
        await target_db.evidence.create_index(
            [("case_id", pymongo.ASCENDING), ("sha256_hash", pymongo.ASCENDING)],
            unique=True,
            name="idx_evidence_case_sha256_unique",
        )
        await target_db.evidence.create_index(
            [("status", pymongo.ASCENDING), ("heartbeat_at", pymongo.ASCENDING)],
            name="idx_evidence_status_heartbeat",
        )

        # Events Collection Indexes
        await target_db.events.create_index(
            [("event_id", pymongo.ASCENDING)],
            unique=True,
            name="idx_events_event_id_unique",
        )
        await target_db.events.create_index(
            [
                ("user_id", pymongo.ASCENDING),
                ("case_id", pymongo.ASCENDING),
                ("is_active", pymongo.ASCENDING),
            ],
            name="idx_events_user_case_active",
        )
        await target_db.events.create_index(
            [
                ("user_id", pymongo.ASCENDING),
                ("case_id", pymongo.ASCENDING),
                ("evidence_id", pymongo.ASCENDING),
                ("is_active", pymongo.ASCENDING),
            ],
            name="idx_events_user_case_evidence_active",
        )
        await target_db.events.create_index(
            [("case_id", pymongo.ASCENDING), ("decision_state", pymongo.ASCENDING)],
            name="idx_events_case_decision_state",
        )
        await target_db.events.create_index(
            [("case_id", pymongo.ASCENDING), ("event_type", pymongo.ASCENDING)],
            name="idx_events_case_event_type",
        )
        await target_db.events.create_index(
            [("evidence_id", pymongo.ASCENDING), ("processing_version", pymongo.ASCENDING)],
            name="idx_events_evidence_version",
        )
        await target_db.events.create_index(
            [("evidence_id", pymongo.ASCENDING), ("processing_run_id", pymongo.ASCENDING)],
            name="idx_events_evidence_run",
        )

        # Finding Reviews Collection Indexes
        await target_db.finding_reviews.create_index(
            [("review_id", pymongo.ASCENDING)],
            unique=True,
            name="idx_reviews_review_id_unique",
        )
        await target_db.finding_reviews.create_index(
            [
                ("case_id", pymongo.ASCENDING),
                ("finding_id", pymongo.ASCENDING),
                ("is_active", pymongo.ASCENDING),
            ],
            name="idx_reviews_case_finding_active",
        )
        await target_db.finding_reviews.create_index(
            [("case_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
            name="idx_reviews_case_created",
        )
        await target_db.finding_reviews.create_index(
            [("finding_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
            name="idx_reviews_finding_created",
        )

        logger.info("MongoDB collection indexes initialized successfully.")
    except Exception as exc:
        logger.warning("Could not initialize MongoDB indexes: %s", str(exc))
