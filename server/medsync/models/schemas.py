"""Pydantic API request/response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ConditionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fhir_id: str
    code: str | None = None
    system: str | None = None
    display: str | None = None
    clinical_status: str | None = None
    onset_date: date | None = None
    has_incomplete_data: bool
    # Stage 2 normalization output
    snomed_code: str | None = None
    icd10_code: str | None = None
    mapping_confidence: float | None = None
    normalized: bool = False
    normalization_failed: bool = False


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fhir_id: str
    family_name: str | None = None
    given_name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    city: str | None = None
    state: str | None = None
    has_incomplete_data: bool
    cluster_id: str | None = None
    match_zone: str | None = None


class PatientDetail(PatientOut):
    address_line: str | None = None
    postal_code: str | None = None
    conditions: list[ConditionOut] = []


class PipelineRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bundle_filename: str | None = None
    status: str
    current_stage: str | None = None
    record_count: int
    error_count: int
    created_at: datetime


class BundleUploadResponse(BaseModel):
    pipeline_run_id: int
    status: str
