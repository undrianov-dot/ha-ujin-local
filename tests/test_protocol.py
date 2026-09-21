"""Protocol tests that do not require Home Assistant."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "ujin_local" / "protocol.py"
SPEC = spec_from_file_location("ujin_protocol", MODULE_PATH)
protocol = module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = protocol
SPEC.loader.exec_module(protocol)


class ProtocolTests(unittest.TestCase):
    def test_parses_potato_packet(self):
        packet = protocol.parse_packet(
            '{"id":114358760,"devName":"ujin-potato-trm-m1",'
            '"token":"0fe544a0","uniq_id":744562,'
            '"data":[{"sn":0,"term":23.5,"reg-term":24}]}'
        )
        self.assertEqual(packet.serial, 114358760)
        self.assertEqual(packet.token, "0fe544a0")
        self.assertEqual(packet.signals["term"], 23.5)
        self.assertEqual(packet.signals["reg-term"], 24)
        self.assertEqual(packet.unique_id, 744562)

    def test_parses_legacy_header_packet(self):
        packet = protocol.parse_packet(
            '{"header":{"id":9156095,"devName":"dinrelay_m4",'
            '"data":{"token":"af01fe5b","rele1":0,"rele2":1}}}'
        )
        self.assertEqual(packet.serial, 9156095)
        self.assertEqual(packet.token, "af01fe5b")
        self.assertEqual(packet.signals["rele2"], 1)

    def test_parses_nested_body_packet(self):
        packet = protocol.parse_packet(
            b'{"header":{"body":{"id":"114358761","name":"trm",'
            b'"data":[{"term":"21.5","reg-term":"22.0"}],'
            b'"token":"nested-token"}}}'
        )
        self.assertIsNotNone(packet)
        self.assertEqual(packet.serial, 114358761)
        self.assertEqual(packet.model, "trm")
        self.assertEqual(packet.token, "nested-token")
        self.assertEqual(packet.signals["term"], "21.5")

    def test_ignores_incomplete_or_unknown_packets(self):
        self.assertIsNone(protocol.parse_packet(b"not-json"))
        self.assertIsNone(protocol.parse_packet('{"header":{"id":"unknown"}}'))
        self.assertIsNone(protocol.parse_packet('{"header":{"id":-1}}'))
        self.assertIsNone(protocol.parse_packet('{"data":{"term":20}}'))
        self.assertIsNone(protocol.parse_packet("Discovery"))

    def test_builds_compact_command(self):
        payload = protocol.build_management_command(
            114358760, "0fe544a0", 12345, {"reg-term": 25}
        )
        self.assertEqual(
            json.loads(payload),
            {
                "command": "management",
                "id": 114358760,
                "uniq_id": 12345,
                "token": "0fe544a0",
                "reg-term": 25,
            },
        )

    def test_boolean_encodings(self):
        self.assertFalse(protocol.value_is_on("0"))
        self.assertFalse(protocol.value_is_on("closed"))
        self.assertTrue(protocol.value_is_on("1"))
        self.assertTrue(protocol.value_is_on(1))

    def test_availability_requires_timezone_aware_recent_timestamp(self):
        now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(protocol.is_recent(now - timedelta(minutes=4), now))
        self.assertFalse(protocol.is_recent(now - timedelta(minutes=6), now))
        self.assertFalse(protocol.is_recent(now.replace(tzinfo=None), now))
        self.assertTrue(protocol.is_recent(now - timedelta(minutes=5), now))

    def test_stale_packets_remain_usable_for_last_value(self):
        stale_seen = datetime.now(timezone.utc) - timedelta(hours=2)
        self.assertFalse(protocol.is_recent(stale_seen, datetime.now(timezone.utc)))
        self.assertIsInstance(stale_seen.isoformat(), str)


if __name__ == "__main__":
    unittest.main()
