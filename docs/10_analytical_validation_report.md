<!--
Document: Analytical Validation Report
Status: NOT DRAFTED — template only
Owner: Anurag Yadav
Last reviewed: -
Change history: docs/13_change_control_log.md
-->

# Analytical Validation Report

> **Status: template.** This document has not been drafted. Fill it in before
> writing any code that depends on it — see CLAUDE.md rule 1.

## 1. Objective

Quantify cross-vendor generalisation of retinal OCT fluid segmentation.

## 2. Method

## 3. Results — segmentation

| Fold | Vendor | Class | Dice [95% CI] | HD95 mm [95% CI] | n patients |
|---|---|---|---|---|---|

## 4. Results — detection

| Fold | Vendor | Class | Sensitivity [95% CI] | Specificity [95% CI] | AUROC [95% CI] |
|---|---|---|---|---|---|

## 5. Generalisation gap

| Class | In-domain Dice | Held-out vendor Dice | Gap |
|---|---|---|---|

## 6. Calibration

## 7. Failure modes

## 8. Limitations

> The rest of this document is still a template. **§8.1 is populated ahead of results
> deliberately**, because it constrains how the headline number must be read and was
> decided when the preprocessing was designed, not after the number was seen. Writing it
> afterwards would make it look like an explanation for whatever the result turned out
> to be.

### 8.1 The measured cross-vendor gap is a LOWER BOUND on the raw-data gap

**Every reported cross-vendor figure is obtained after per-volume intensity
normalisation** (SRS-070): the 1st and 99th percentiles of each volume are mapped to 0
and 1 and values outside are clipped. This removes the part of the vendor difference
that is a difference in encoding rather than in imaging, so **the generalisation gap in
§5 is smaller than the gap raw data would produce.** It is a lower bound, and no figure
in this document should be read as the degradation a naive pipeline would suffer.

**What specifically is removed.** The clearest case is Topcon, which carries a raised
black level: measured across the training partition, its 1st percentile is **35/255**,
against 0/255 for Cirrus and 0/65535 for Spectralis. That is a detector offset, not
tissue. Under dtype-maximum scaling it survives as a constant brightness offset
**perfectly correlated with vendor** — measured median as a fraction of full scale is
0.122 for Cirrus, 0.132 for Spectralis and 0.235 for Topcon, so two vendors coincide and
the third is separated by a factor of nearly two for a reason that has nothing to do with
retinal anatomy. A network can read vendor identity straight off the brightness, and a
model that does so scores well in domain and has learned nothing that transfers.

**Why removing it is defensible rather than convenient.** Three reasons, and the first is
the one that matters:

1. **Leaving it in would not measure vendor shift, it would measure a bug.** A gap driven
   by an uncorrected detector offset is not evidence about whether segmentation
   transfers across scanners; it is evidence that the preprocessing was wrong. The
   residual gap after normalisation is attributable to speckle, axial resolution,
   sampling density and population differences — the things the question is actually
   about.
2. **Any deployable system would normalise.** Reporting the un-normalised gap would
   describe a system nobody would build.
3. **The correction uses no information the held-out vendor does not carry itself.** The
   window is computed from each volume individually, so the held-out vendor is treated
   identically to the training vendors and nothing about the training distribution
   leaks into test preprocessing.

**What is not claimed.** Normalisation does not remove vendor shift; it removes the
trivially correctable component. Speckle statistics, axial resolution (a factor of two
between Cirrus and Spectralis before resampling), B-scan density (49 against 128) and
field of view all differ and all survive. Those are the shift this project measures.

**How to quantify what was removed.** §5's gap can be compared against a fold trained
with dtype-maximum scaling instead of the percentile window, which would isolate the
pedestal's contribution. That run is **conditional on quota** and is not part of the
primary result; if it was not run, this section stands as a stated bound rather than a
measured one, and says so here rather than leaving the reader to assume either.

### 8.2 Axial resampling

All frames are resampled axially to a declared 0.004 mm/pixel (SRS-072). The target is
the **coarsest** common choice, so no vendor is ever upsampled: upsampling would
fabricate detail and could substitute a smoothness signature for the brightness one
removed above. Cirrus is downsampled by a factor of about two and loses real axial
detail; that cost is accepted and is measurable by comparison against a native-resolution
run. All metrics and all volumes in mm³ are computed in native geometry (SRS-074), so no
reported number is expressed at the resampled spacing.

## 9. Conclusion
