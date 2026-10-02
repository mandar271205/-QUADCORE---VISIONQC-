from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.db.models import Decision, Severity, ClientType


class DefectRegion(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., ge=0.0, le=1.0)
    height: float = Field(..., ge=0.0, le=1.0)


class DefectResponse(BaseModel):
    type: str
    description: Optional[str] = None
    severity: Severity
    region: Optional[DefectRegion] = None

    model_config = {"from_attributes": True}
