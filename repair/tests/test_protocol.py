"""Frozen repair-v2 protocol metadata tests."""

import unittest

from repair.protocol import bulk_confirmation_required, validate_repair_protocol


class ProtocolTests(unittest.TestCase):
    def test_bulk_online_calls_require_explicit_confirmation(self) -> None:
        self.assertFalse(bulk_confirmation_required("openai-compatible", 9, False))
        self.assertTrue(bulk_confirmation_required("openai-compatible", 10, False))
        self.assertFalse(bulk_confirmation_required("openai-compatible", 150, True))
        self.assertFalse(bulk_confirmation_required("fake", 150, False))

    def test_registered_implementation_hashes(self) -> None:
        protocol = validate_repair_protocol()
        self.assertEqual("repair-v2", protocol["protocol_version"])
        self.assertEqual("fl-v1", protocol["fl_method_version"])
        self.assertEqual(1, protocol["attempts_per_case_group"])


if __name__ == "__main__":
    unittest.main()
