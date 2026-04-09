from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


# Types
class TypeCreate(BaseModel):
    name: str
    unit: str
    value_type: Literal["integer", "float"]
    default_value: float | None = None
    icon: str | None = None


class TypeResponse(BaseModel):
    id: int
    name: str
    unit: str
    value_type: Literal["integer", "float"]
    default_value: float | None
    icon: str | None
    created_at: datetime


# Entries
class EntryCreate(BaseModel):
    type_id: int
    value: float
    notes: str | None = None

    @field_validator("value")
    @classmethod
    def value_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("value must be positive")
        return v


class EntryResponse(BaseModel):
    id: int
    type_id: int
    type_name: str
    type_unit: str
    value: float
    notes: str | None
    created_at: datetime


# Auth
class LoginRequest(BaseModel):
    api_key: str


# General
class MessageResponse(BaseModel):
    message: str
