"""Pydantic models matching Supabase tables."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from typing import Optional


class BusinessUnit(BaseModel):
    id: UUID
    code: str
    description: Optional[str] = None
    createdAt: Optional[datetime] = Field(None, alias="createdAt")
    updatedAt: Optional[datetime] = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class Equipment(BaseModel):
    id: UUID
    businessUnitId: Optional[UUID] = Field(None, alias="businessUnitId")
    code: str
    description: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    serialNumber: Optional[str] = Field(None, alias="serialNumber")
    gpsDeviceTag: Optional[str] = Field(None, alias="gpsDeviceTag")
    hourMeter: Optional[int] = Field(None, alias="hourMeter")
    odometer: Optional[int] = None
    isRental: Optional[bool] = Field(None, alias="isRental")
    isActive: Optional[bool] = Field(None, alias="isActive")
    createdAt: Optional[datetime] = Field(None, alias="createdAt")
    updatedAt: Optional[datetime] = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class Job(BaseModel):
    id: UUID
    businessUnitId: Optional[UUID] = Field(None, alias="businessUnitId")
    code: str
    description: Optional[str] = None
    createdAt: Optional[datetime] = Field(None, alias="createdAt")
    updatedAt: Optional[datetime] = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class Location(BaseModel):
    id: UUID
    businessUnitId: Optional[UUID] = Field(None, alias="businessUnitId")
    code: str
    description: Optional[str] = None
    createdAt: Optional[datetime] = Field(None, alias="createdAt")
    updatedAt: Optional[datetime] = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}
