"""FastAPI inference service.

Traces to: SRS-TBD (inference API)

No web UI — this is an API and a document set. Every response carries the
scan-level confidence and the review_recommended flag; a caller must not be able
to receive a segmentation without also receiving its uncertainty.
"""

from __future__ import annotations

from fastapi import FastAPI

from ocuval import __version__
from ocuval.service.schemas import HealthResponse

app = FastAPI(
    title="OcuVal inference service",
    version=__version__,
    description="Retinal OCT fluid segmentation. Not for clinical use.",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


# POST /infer — accepts a DICOM series, returns InferenceResponse and stores the
# resulting SEG and SR objects to the configured PACS. Not yet implemented.
