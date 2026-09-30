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
    def test_unsigned_serial_and_envelope_ack_id(self):
        packet = protocol.parse_packet(json.dumps({
            "header": {"id": 4187268204, "uniq_id": 123,
                       "body": {"data": {"treg": 12}}}
        }))
        self.assertEqual(packet.serial, 4187268204)
        self.assertEqual(packet.unique_id, 123)
        self.assertEqual(packet.signals["treg"], 12)

    def test_top_level_ack_id_with_body(self):
        packet = protocol.parse_packet(json.dumps({
            "uniq_id": "456", "header": {"body": {"id": 17, "data": {"term": 25}}}
        }))
        self.assertEqual(packet.unique_id, "456")

    def test_whole_degree_rounding_and_validation(self):
        for value, expected in [(21, 21), (21.2, 21), (21.5, 22), (22.5, 23), ("24", 24)]:
            self.assertEqual(protocol.whole_degree(value), expected)
        for value in (None, True, "bad", "nan", float("inf"), 4.9, 40.1):
            with self.assertRaises(ValueError):
                protocol.whole_degree(value)

    def test_mesh_uses_advertised_private_address_and_device_port(self):
        self.assertEqual(protocol.command_endpoint({"ip": "192.168.1.27", "udpp": 30300}, "192.168.1.23", 9999), ("192.168.1.27", 30300))
        for address in ("bad", "0.0.0.0", "127.0.0.1", "8.8.8.8", "224.0.0.1", "255.255.255.255"):
            self.assertEqual(protocol.command_endpoint({"ip": address, "udpp": -1}, "192.168.1.27", 30300), ("192.168.1.27", 30300))
        self.assertEqual(protocol.command_endpoint({"udpp": 30300.5}, "192.168.1.27", 30300)[1], 30300)

    def test_finite_measurements(self):
        for value in (None, True, float("nan"), float("inf")):
            self.assertIsNone(protocol.finite_number(value))
        self.assertEqual(protocol.finite_number("27.9"), 27.9)

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
        self.assertEqual(float(packet.signals["reg-term"]), 24.0)

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

    def test_parses_string_setpoint_from_device_packet(self):
        packet = protocol.parse_packet(
            '{"id":114358762,"devName":"ujin-potato-trm-m1",'
            '"data":[{"term":"20.5","reg-term":"21.5"}]}'
        )
        self.assertIsNotNone(packet)
        self.assertEqual(float(packet.signals["term"]), 20.5)
        self.assertEqual(float(packet.signals["reg-term"]), 21.5)


if __name__ == "__main__":
    unittest.main()

