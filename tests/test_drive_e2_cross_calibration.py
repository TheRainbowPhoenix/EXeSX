"""Firmware-free E2 raw electrode calibration and fail-closed controls."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from drive_e2_cross import fit_raw_to_screen, screen_to_raw, sample_lines


class E2PhysicalCalibrationTests(unittest.TestCase):
    def points(self):
        return [
            {"raw": [200, 300], "screen": [60, 30]},
            {"raw": [1200, 1300], "screen": [310, 180]},
            {"raw": [2200, 2300], "screen": [560, 330]},
        ]

    def test_inverse_linear_map_is_measured_not_fullrange_guess(self):
        model = fit_raw_to_screen(self.points())
        self.assertAlmostEqual(model[0][0], .25)
        self.assertAlmostEqual(model[0][1], 10)
        self.assertAlmostEqual(model[1][0], .15)
        self.assertAlmostEqual(model[1][1], -15)
        self.assertEqual(screen_to_raw(310, 180, calibration=model), (1200, 1300))
        line = list(sample_lines([((60, 30), (310, 180))],
                                 sample_px=2000, calibration=model))
        self.assertEqual(line, [[(200, 300), (1200, 1300)]])

    def test_missing_outside_and_nonlinear_samples_fail(self):
        with self.assertRaises(ValueError):
            fit_raw_to_screen(self.points()[:1])
        with self.assertRaises(ValueError):
            fit_raw_to_screen([{"raw": [200, 300], "screen": [60, 30]},
                               {"raw": [200, 1300], "screen": [70, 180]}])
        distorted = self.points()
        distorted[2] = {"raw": [2200, 2300], "screen": [840, 330]}
        with self.assertRaises(ValueError):
            fit_raw_to_screen(distorted)
        model = fit_raw_to_screen(self.points())
        with self.assertRaises(ValueError):
            screen_to_raw(863, 479, calibration=model)
        with self.assertRaises(ValueError):
            screen_to_raw(60, 30, calibration=model, swap_axes=True)


if __name__ == "__main__":
    unittest.main()
