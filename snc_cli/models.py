"""Pydantic models matching Supabase tables."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BusinessUnit(BaseModel):
    id: UUID
    code: str
    description: str | None = None
    createdAt: datetime | None = Field(None, alias="createdAt")
    updatedAt: datetime | None = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class Equipment(BaseModel):
    id: UUID
    businessUnitId: UUID | None = Field(None, alias="businessUnitId")
    code: str
    description: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    serialNumber: str | None = Field(None, alias="serialNumber")
    gpsDeviceTag: str | None = Field(None, alias="gpsDeviceTag")
    hourMeter: int | None = Field(None, alias="hourMeter")
    odometer: int | None = None
    isRental: bool | None = Field(None, alias="isRental")
    isActive: bool | None = Field(None, alias="isActive")
    createdAt: datetime | None = Field(None, alias="createdAt")
    updatedAt: datetime | None = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class Job(BaseModel):
    id: UUID
    businessUnitId: UUID | None = Field(None, alias="businessUnitId")
    code: str
    description: str | None = None
    createdAt: datetime | None = Field(None, alias="createdAt")
    updatedAt: datetime | None = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class Location(BaseModel):
    id: UUID
    businessUnitId: UUID | None = Field(None, alias="businessUnitId")
    code: str
    description: str | None = None
    createdAt: datetime | None = Field(None, alias="createdAt")
    updatedAt: datetime | None = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}
