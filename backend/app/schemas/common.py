"""Public timestamps always identify UTC, including SQLite's naive values."""
from datetime import datetime, timezone
from pydantic import BaseModel, field_validator


class UTCResponse(BaseModel):
    @field_validator('*', mode='after')
    @classmethod
    def utc_timestamps(cls, value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
