"""Frozen repair-v1 protocol metadata tests."""

import unittest

from repair.protocol import validate_repair_protocol


class ProtocolTests(unittest.TestCase):
    def test_registered_implementation_hashes(self) -> None:
        protocol = validate_repair_protocol()
        self.assertEqual("repair-v1", protocol["protocol_version"])
        self.assertEqual("fl-v1", protocol["fl_method_version"])
        self.assertEqual(1, protocol["attempts_per_case_group"])


if __name__ == "__main__":
    unittest.main()
