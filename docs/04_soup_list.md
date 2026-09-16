<!--
Document: SOUP List
Status: NOT DRAFTED — template only
Owner: Anurag Yadav
Last reviewed: -
Change history: docs/13_change_control_log.md
-->

# SOUP List

> **Status: template.** This document has not been drafted. Fill it in before
> writing any code that depends on it — see CLAUDE.md rule 1.

Software of Unknown Provenance. Every pinned dependency in `pyproject.toml` appears
here. Adding a dependency without adding a row is a defect.

| ID | Component | Version | Purpose | Requirements it supports | Known anomalies reviewed | Risk notes |
|---|---|---|---|---|---|---|
| SOUP-001 | pydicom | 2.4.4 | DICOM read/write | | | |
| SOUP-002 | highdicom | 0.22.0 | SEG / SR construction | | | |
| SOUP-003 | MONAI | 1.3.2 | Transforms, networks, metrics | | | |
| SOUP-004 | PyTorch | 2.3.1 | Training and inference | | | |
| SOUP-005 | SimpleITK | 2.3.1 | MetaImage reading, resampling | | | |
| SOUP-006 | NumPy | 1.26.4 | Array operations | | | |
| SOUP-007 | SciPy | 1.13.1 | Distance transforms for HD95 | | | |
| SOUP-008 | scikit-learn | 1.5.1 | AUROC, calibration | | | |
| SOUP-009 | FastAPI | 0.111.1 | Inference API | | | |
| SOUP-010 | uvicorn | 0.30.3 | ASGI server | | | |
| SOUP-011 | pandas | 2.2.2 | Manifest and results tables | | | |
| SOUP-012 | requests | 2.32.3 | DICOMweb client | | | |
| SOUP-013 | PyYAML | 6.0.2 | Configuration | | | |
| SOUP-014 | Orthanc | 24.7.3 | Local PACS (test environment only) | | | |
