import unittest
from copy import deepcopy
from unittest.mock import patch
import wheat_q0_conditional_relay as gate
import wheat_source_collision_controls as controls


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.old = {g: dict(has_path=True, selected_reference_bp=900, source_slice_n50=500, slices=7)
                    for g in controls.CONTROLS}
        self.new = deepcopy(self.old)

    def test_exact_or_better_per_group(self):
        self.assertTrue(controls.compare(self.old, self.new)["passed"])
        self.new["3B"].update(selected_reference_bp=950, source_slice_n50=600, slices=5)
        self.assertTrue(controls.compare(self.old, self.new)["passed"])

    def test_any_single_regression_holds_even_if_other_group_improves(self):
        self.new["3D"].update(selected_reference_bp=1000, source_slice_n50=600, slices=2)
        for k, value in (("selected_reference_bp", 899), ("source_slice_n50", 499), ("slices", 8)):
            with self.subTest(field=k), patch.dict(self.new["1A"], {k: value}):
                self.assertFalse(controls.compare(self.old, self.new)["passed"])

    def test_bad_or_missing_metrics_cannot_pass(self):
        for k, value in (("has_path", False), ("slices", True), ("source_slice_n50", 0)):
            with self.subTest(field=k), patch.dict(self.new["3B"], {k: value}), self.assertRaises(ValueError):
                controls.compare(self.old, self.new)
        del self.new["3D"]
        with self.assertRaises(KeyError): controls.compare(self.old, self.new)

    def test_adfe_cannot_fall_back_to_legacy_authorization(self):
        cfg = {"runtime_revision":gate.SOURCE_REVISION, "engine_revision":"2064"}
        with self.assertRaises(ValueError): gate.verify_engineering_binding(cfg, {}, {"source_revision":gate.SOURCE_REVISION})
        source = dict(engine_commit=gate.SOURCE_REVISION, scientific_baseline_commit=gate.SOURCE_PARENT,
                      selector_identity="q0-selector-37bb033a42a3772eae997621", path_policy={"reference_locus_padding_bp":100000},
                      tools_sha256=gate.SOURCE_ARCHIVE)
        gate.verify_validation_source(cfg, source)
        with self.assertRaises(ValueError): gate.verify_validation_source(cfg, dict(source,tools_sha256="old"))
