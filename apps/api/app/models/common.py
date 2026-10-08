from datetime import datetime, timezone
from typing import Annotated, Any
from bson import ObjectId
from pydantic import BeforeValidator, PlainSerializer

# Pydantic v2 compatible ObjectId representation
PyObjectId = Annotated[
    str,
    BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v),
    PlainSerializer(lambda v: str(v), return_type=str),
]


def utc_now() -> datetime:
    """Returns the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)
