"""Request and response models for the inference service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    model_id: str | None = None


class InferenceResponse(BaseModel):
    """Result of one inference request."""

    study_instance_uid: str
    series_instance_uid: str
    seg_sop_instance_uid: str
    sr_sop_instance_uid: str
    volumes_mm3: dict[str, float] = Field(description="Fluid volume per class")
    confidence: float = Field(description="Scan-level MC-dropout confidence, 0-1")
    review_recommended: bool = Field(
        description="True when confidence falls below the configured threshold"
    )
