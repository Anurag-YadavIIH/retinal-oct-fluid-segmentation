"""TC-001 — the fixed parts of the data configuration must not drift.

Label indices and vendor keys are frozen (CLAUDE.md section 4). Reordering them
silently invalidates every trained checkpoint and every reported metric, so the
contract is asserted in CI rather than trusted.
"""

from __future__ import annotations

EXPECTED_LABELS = {"background": 0, "IRF": 1, "SRF": 2, "PED": 3}
EXPECTED_VENDORS = ["cirrus", "spectralis", "topcon"]


def test_TC_001_label_indices_are_frozen(data_config):
    assert data_config["labels"] == EXPECTED_LABELS


def test_TC_001_label_names_match_indices(data_config):
    names = data_config["label_names"]
    for name, idx in EXPECTED_LABELS.items():
        assert names[idx] == name


def test_TC_001_vendors_are_frozen(data_config):
    assert data_config["vendors"] == EXPECTED_VENDORS


def test_TC_001_seed_is_present(data_config):
    assert isinstance(data_config["seed"], int)
