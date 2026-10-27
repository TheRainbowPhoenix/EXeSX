"""Original A7 SERVICE/password event audit: isolated, fabricated records."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_original_service_password.py"
spec = importlib.util.spec_from_file_location("audit_original_service_password", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def observed(keys, last_type=0x17):
    return [{"type": (last_type if i == 4 else 0x17), "code": key}
            for i, key in enumerate(keys)]


class OriginalServicePasswordAuditTests(unittest.TestCase):
    def test_mode1_service_unlock_exact_five_key_events(self):
        keys = [0x91, 0x93, 0x90, 0x92, 0x94]
        self.assertTrue(mod.audit(observed(keys), 1)["accepted"])
        self.assertTrue(mod.audit(observed(keys, last_type=0x12), 1)["accepted"])
        self.assertFalse(mod.audit(observed(keys), 0)["accepted"])

    def test_mode0_protected_operations_differs_from_service_mode(self):
        keys = [0x91, 0x93, 0x93, 0x92, 0x94]
        self.assertTrue(mod.audit(observed(keys), 0)["accepted"])
        self.assertFalse(mod.audit(observed(keys), 1)["accepted"])

    def test_extra_enter_or_wrong_event_type_is_detected(self):
        expected = [0x91, 0x93, 0x90, 0x92, 0x94]
        stale = observed([0x94] + expected[:4])
        self.assertEqual(mod.audit(stale, 1)["first_rejected_position"], 1)
        wrong = observed(expected)
        wrong[2]["type"] = "0x16"
        self.assertEqual(mod.audit(wrong, 1)["first_rejected_position"], 3)
        with self.assertRaises(ValueError):
            mod.audit(observed(expected)[:4], 1)


if __name__ == "__main__":
    unittest.main()
