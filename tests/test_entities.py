"""Isolated runtime tests with small HA interface doubles (no real network)."""

import asyncio
from datetime import datetime, timedelta, timezone
from enum import Enum, IntFlag
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1] / "custom_components" / "ujin_local"


def load_modules():
    stubs = {}
    def module(name, **values):
        item = ModuleType(name)
        item.__dict__.update(values)
        stubs[name] = item
        return item

    class Entity:
        hass = None
        def async_write_ha_state(self):
            pass
    class Climate(Entity):
        @property
        def min_temp(self):
            return self._attr_min_temp
        @property
        def max_temp(self):
            return self._attr_max_temp
    class Features(IntFlag):
        TARGET_TEMPERATURE = 1
    class HVAC(Enum):
        HEAT = "heat"
        HEATING = "heating"
        IDLE = "idle"
    module("homeassistant")
    module("homeassistant.components")
    module("homeassistant.components.climate", ClimateEntity=Climate, ClimateEntityFeature=Features, HVACAction=HVAC, HVACMode=HVAC)
    module("homeassistant.components.number", NumberEntity=Entity, NumberMode=SimpleNamespace(SLIDER="slider", BOX="box"))
    module("homeassistant.components.binary_sensor", BinarySensorEntity=Entity,
           BinarySensorDeviceClass=SimpleNamespace(MOISTURE="moisture", CONNECTIVITY="connectivity"))
    module("homeassistant.components.switch", SwitchEntity=Entity, SwitchDeviceClass=SimpleNamespace(SWITCH="switch"))
    module("homeassistant.components.sensor", SensorEntity=Entity, SensorDeviceClass=SimpleNamespace(
        TEMPERATURE="temperature", HUMIDITY="humidity", ATMOSPHERIC_PRESSURE="atmospheric_pressure",
        SOUND_PRESSURE="sound_pressure", CO2="carbon_dioxide", ILLUMINANCE="illuminance", SIGNAL_STRENGTH="signal_strength"
    ), SensorStateClass=SimpleNamespace(MEASUREMENT="measurement"))
    module("homeassistant.config_entries", ConfigEntry=object)
    module("homeassistant.const", ATTR_TEMPERATURE="temperature", UnitOfTemperature=SimpleNamespace(CELSIUS="�C"),
           UnitOfPressure=SimpleNamespace(PA="Pa"), UnitOfRatio=SimpleNamespace(PARTS_PER_MILLION="ppm"),
           LIGHT_LUX="lx", SIGNAL_STRENGTH_DECIBELS_MILLIWATT="dBm")
    module("homeassistant.core", HomeAssistant=object, callback=lambda f: f)
    module("homeassistant.exceptions", HomeAssistantError=RuntimeError)
    module("homeassistant.helpers")
    module("homeassistant.helpers.entity", Entity=Entity, EntityCategory=SimpleNamespace(CONFIG="config", DIAGNOSTIC="diagnostic"))
    module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    module("homeassistant.helpers.device_registry", DeviceInfo=lambda **kwargs: kwargs)
    module("homeassistant.helpers.event", async_track_time_interval=lambda *a: None)
    module("homeassistant.helpers.dispatcher", async_dispatcher_send=lambda *a: None, async_dispatcher_connect=lambda *a: None)
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    package = module("ujin_test_runtime")
    package.__path__ = [str(ROOT)]
    sys.modules[package.__name__] = package
    loaded = {}
    try:
        for name in ("const", "protocol", "hub", "entity", "climate", "number", "switch", "sensor", "binary_sensor", "diagnostics"):
            spec = importlib.util.spec_from_file_location(f"{package.__name__}.{name}", ROOT / f"{name}.py")
            item = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = item
            spec.loader.exec_module(item)
            loaded[name] = item
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return loaded


MODULES = load_modules()
hub_module = MODULES["hub"]


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def make_hub(self, data=None):
        updates = []
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=lambda *a, **kw: updates.append(kw)))
        entry = SimpleNamespace(data=data or {})
        hub = hub_module.UjinHub(hass, entry, 9999)
        hub.devices[4187268204] = hub_module.UjinDevice(4187268204, "ujin-potato-trm-m1", "192.168.1.27", token="dummy")
        return hub, updates

    async def test_command_ack_and_mesh_routing(self):
        hub, _ = self.make_hub()
        sent = []
        def send(payload, address):
            sent.append((json.loads(payload), address))
            ack = {"header": {"id": 4187268204, "uniq_id": sent[-1][0]["uniq_id"], "body": {"data": {"treg": 13}}}}
            asyncio.get_running_loop().call_soon(hub.handle_datagram, json.dumps(ack).encode(), ("192.168.1.23", 30300))
        hub.transport = SimpleNamespace(sendto=send)
        hub.handle_datagram(json.dumps({"id": 4187268204, "data": {"ip": "192.168.1.27", "udpp": 30300}}).encode(), ("192.168.1.23", 30300))
        await hub.async_send_changes(4187268204, {"treg": 13})
        self.assertEqual(sent[0][1], ("192.168.1.27", 30300))
        self.assertEqual(hub.devices[4187268204].ip_address, "192.168.1.27")
        self.assertEqual(hub._pending_commands, {})

    async def test_command_accepts_state_confirmation_without_uniq_id(self):
        hub, _ = self.make_hub()

        def send(payload, address):
            response = {
                "header": {
                    "id": 4187268204,
                    "data": {"treg": "13"},
                }
            }
            asyncio.get_running_loop().call_soon(
                hub.handle_datagram,
                json.dumps(response).encode(),
                ("192.168.1.27", 30300),
            )

        hub.transport = SimpleNamespace(sendto=send)
        await hub.async_send_changes(4187268204, {"treg": 13})

        self.assertEqual(hub._pending_commands, {})
        self.assertEqual(hub.devices[4187268204].signals["treg"], "13")

    async def test_old_state_does_not_confirm_requested_temperature(self):
        hub, _ = self.make_hub()

        def send(payload, address):
            response = {
                "header": {
                    "id": 4187268204,
                    "data": {"treg": 12},
                }
            }
            asyncio.get_running_loop().call_soon(
                hub.handle_datagram,
                json.dumps(response).encode(),
                ("192.168.1.27", 30300),
            )

        hub.transport = SimpleNamespace(sendto=send)
        with patch.object(
            hub_module, "COMMAND_ACK_TIMEOUT", timedelta(milliseconds=1)
        ):
            with self.assertRaisesRegex(RuntimeError, "did not confirm the requested value"):
                await hub.async_send_changes(4187268204, {"treg": 13})

        self.assertEqual(hub._pending_commands, {})

    async def test_cancelled_command_does_not_block_device(self):
        hub, _ = self.make_hub()
        hub.transport = SimpleNamespace(sendto=lambda *a: None)
        task = asyncio.create_task(hub.async_send_changes(4187268204, {"treg": 13}))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(hub._pending_commands, {})

    async def test_send_error_does_not_block_device(self):
        hub, _ = self.make_hub()
        pending_futures = []
        def send(*a):
            pending_futures.append(hub._pending_commands[4187268204][1])
            raise OSError("test error")
        hub.transport = SimpleNamespace(sendto=send)
        with self.assertRaises(RuntimeError):
            await hub.async_send_changes(4187268204, {"treg": 13})
        self.assertEqual(hub._pending_commands, {})
        self.assertTrue(pending_futures[0].cancelled())

    async def test_step_and_real_setpoint_priority(self):
        hub, _ = self.make_hub()
        sent = []
        async def send(serial, changes):
            sent.append(changes)
        hub.async_send_changes = send
        device = hub.devices[4187268204]
        device.signals = {"term": 27.9, "treg": 12, "reg-term": 30}
        climate = MODULES["climate"].UjinThermostat(hub, device.serial)
        self.assertEqual(climate.target_temperature, 12)
        self.assertEqual(climate._attr_target_temperature_step, 1)
        await climate.async_set_temperature(temperature=13.5)
        self.assertEqual(sent, [{"treg": 14}])
        device.signals = {"term": 27.9}
        self.assertIsNone(climate.target_temperature)
        await climate.async_set_temperature(temperature=14)
        self.assertEqual(sent[-1], {"treg": 14})
        device.last_seen = datetime.now(timezone.utc) - timedelta(minutes=6)
        self.assertTrue(climate.available)
        self.assertEqual(climate.current_temperature, 27.9)
        self.assertEqual(climate.target_temperature, 14)

    async def test_last_seen_persistence_is_throttled_but_critical_changes_are_immediate(self):
        hub, updates = self.make_hub()
        device = hub.devices[4187268204]
        device.signals = {"term": 27.9}
        hub._persist_device(device)
        self.assertEqual(len(updates), 1)

        saved_seen = device.last_seen
        device.last_seen = saved_seen + timedelta(minutes=4)
        hub._persist_device(device)
        self.assertEqual(len(updates), 1)

        device.last_seen = saved_seen + timedelta(minutes=5, seconds=1)
        hub._persist_device(device)
        self.assertEqual(len(updates), 2)

        device.signals["term"] = 28.1
        device.last_seen += timedelta(seconds=1)
        hub._persist_device(device)
        self.assertEqual(len(updates), 2)

        device.signals["leak"] = 1
        hub._persist_device(device)
        self.assertEqual(len(updates), 3)

    async def test_persistence_keeps_measurements_not_secret_signals(self):
        hub, updates = self.make_hub()
        device = hub.devices[4187268204]
        device.signals = {"term": 27.9, "treg": 12, "br-lcd": 40, "password": "do-not-copy", "schedule": []}
        hub._persist_device(device)
        data = updates[-1]["data"]
        stored = data["devices"][str(device.serial)]
        self.assertEqual(stored["signals"], {"term": 27.9, "treg": 12, "br-lcd": 40})
        restored = hub_module.UjinHub(hub.hass, SimpleNamespace(data=data), 9999)
        self.assertEqual(restored.devices[device.serial].signals, stored["signals"])
        self.assertEqual(restored.devices[device.serial].management_port, 30300)

    async def test_capabilities_are_discovered_from_real_signals(self):
        hub, _ = self.make_hub()
        device = hub.devices[4187268204]
        device.signals = {"term": 27.9, "term-sex": 27.8, "lux": 48, "br-lcd": 40, "kid-bl": 0}
        hass = SimpleNamespace(data={"ujin_local": {"entry": hub}})
        entry = SimpleNamespace(entry_id="entry", async_on_unload=lambda *a: None)
        sensors = []
        await MODULES["sensor"].async_setup_entry(hass, entry, sensors.extend)
        self.assertEqual({item.signal_name for item in sensors}, {"term", "term-sex", "lux"})
        numbers = []
        await MODULES["number"].async_setup_entry(hass, entry, numbers.extend)
        self.assertEqual(len(numbers), 2)
        brightness = next(item for item in numbers if isinstance(item, MODULES["number"].UjinBrightness))
        self.assertEqual(brightness.native_value, 40)
        switches = []
        await MODULES["switch"].async_setup_entry(hass, entry, switches.extend)
        self.assertEqual([item.signal_name for item in switches], ["kid-bl"])
        commands = []
        async def send(serial, changes):
            commands.append(changes)
        hub.async_send_changes = send
        await brightness.async_set_native_value(41)
        await switches[0].async_turn_on()
        self.assertEqual(commands, [{"br-lcd": 41}, {"kid-bl": 1}])
        self.assertEqual(brightness.native_value, 40)  # no optimistic configuration
        with self.assertRaises(RuntimeError):
            await brightness.async_set_native_value(100.5)

    async def test_absolute_setpoint_accepts_owner_value_without_initial_telemetry(self):
        hub, updates = self.make_hub()
        device = hub.devices[4187268204]
        device.signals = {"term": 27.2}
        number = MODULES["number"].UjinSetpoint(hub, device.serial)
        climate = MODULES["climate"].UjinThermostat(hub, device.serial)
        self.assertTrue(number.available)
        self.assertIsNone(number.native_value)
        self.assertEqual(number._attr_native_step, 1)
        self.assertEqual(number._attr_mode, "box")
        commands = []
        async def send(serial, changes):
            commands.append(changes)
        hub.async_send_changes = send
        await number.async_set_native_value(23.7)
        self.assertEqual(commands, [{"treg": 24}])
        self.assertEqual(number.native_value, 24)
        self.assertEqual(climate.target_temperature, 24)
        restored = hub_module.UjinHub(hub.hass, SimpleNamespace(data=updates[-1]["data"]), 9999)
        self.assertEqual(restored.devices[device.serial].signals["treg"], 24)
        for value in (4.9, 40.1, float("nan"), float("inf")):
            with self.assertRaises(RuntimeError):
                await number.async_set_native_value(value)
        self.assertEqual(len(commands), 1)
        device.token = None
        self.assertFalse(number.available)

    async def test_failed_setpoint_is_not_displayed_or_persisted(self):
        hub, updates = self.make_hub()
        device = hub.devices[4187268204]
        number = MODULES["number"].UjinSetpoint(hub, device.serial)
        async def fail(serial, changes):
            raise RuntimeError("no acknowledgement")
        hub.async_send_changes = fail
        with self.assertRaises(RuntimeError):
            await number.async_set_native_value(24)
        self.assertIsNone(number.native_value)
        self.assertEqual(updates, [])

    async def test_valve_and_leak_states_survive_restart_and_heartbeat_only_packets(self):
        hub, updates = self.make_hub()
        serial = 4187322636
        device = hub_module.UjinDevice(serial, "ujin-potato-ld-m1", "192.168.1.12", token="dummy")
        hub.devices[serial] = device
        device.signals = {"rele-w": 1, "leak": 0, "password": "not-a-cached-signal"}
        hub._persist_device(device)
        device.signals["leak"] = 1
        # Critical state changes must bypass the 30-second measurement throttle.
        hub._persist_device(device)
        self.assertEqual(len(updates), 2)
        stored = updates[-1]["data"]["devices"][str(serial)]["signals"]
        self.assertEqual(stored, {"rele-w": 1, "leak": 1})
        restored = hub_module.UjinHub(hub.hass, SimpleNamespace(data=updates[-1]["data"]), 9999)
        restored.handle_datagram(json.dumps({"id": serial, "data": {"time": 1234}}).encode(), (device.ip_address, 30300))
        self.assertEqual(restored.devices[serial].signals["rele-w"], 1)
        self.assertEqual(restored.devices[serial].signals["leak"], 1)
        leak = MODULES["binary_sensor"].UjinBinarySensor(restored, serial, "leak", "Leak", "moisture")
        connection = MODULES["binary_sensor"].UjinBinarySensor(
            restored, serial, "connectivity", "Connection", "connectivity"
        )
        self.assertTrue(leak.available)
        self.assertTrue(leak.is_on)
        restored.devices[serial].last_seen -= timedelta(minutes=6)
        self.assertTrue(leak.available)
        self.assertTrue(leak.is_on)
        self.assertFalse(connection.is_on)

    async def test_connection_is_separate_from_unknown_controller_state(self):
        hub, _ = self.make_hub()
        serial = 4187322636
        hub.devices[serial] = hub_module.UjinDevice(serial, "ujin-potato-ld-m1", "192.168.1.12")
        connection = MODULES["binary_sensor"].UjinBinarySensor(hub, serial, "connectivity", "Connection", "connectivity")
        leak = MODULES["binary_sensor"].UjinBinarySensor(hub, serial, "leak", "Leak", "moisture")
        self.assertTrue(connection.available)
        self.assertTrue(connection.is_on)
        self.assertFalse(leak.available)
        self.assertIsNone(leak.is_on)
        hub.devices[serial].last_seen -= timedelta(minutes=6)
        self.assertTrue(connection.available)
        self.assertFalse(connection.is_on)

    async def test_sensor_and_switch_keep_last_known_values_when_stale(self):
        hub, _ = self.make_hub()
        device = hub.devices[4187268204]
        device.signals = {"term": 27.9, "kid-bl": 1}
        device.last_seen -= timedelta(minutes=6)

        sensor = MODULES["sensor"].UjinSignalSensor(hub, device.serial, "term")
        switch = MODULES["switch"].UjinSignalSwitch(
            hub, device.serial, "kid-bl", "Child lock", False
        )

        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 27.9)
        self.assertTrue(switch.available)
        self.assertTrue(switch.is_on)

    async def test_diagnostics_redacts_nested_secrets(self):
        hub, _ = self.make_hub()
        device = hub.devices[4187268204]
        device.signals = {
            "term": 21.5,
            "metadata": {"TOKEN": "secret", "nested": [{"password": "secret"}]},
        }
        hass = SimpleNamespace(data={"ujin_local": {"entry": hub}})
        entry = SimpleNamespace(entry_id="entry")

        diagnostics = await MODULES["diagnostics"].async_get_config_entry_diagnostics(
            hass, entry
        )

        signals = diagnostics["devices"][str(device.serial)]["signals"]
        self.assertEqual(signals["term"], 21.5)
        self.assertEqual(signals["metadata"]["TOKEN"], "**REDACTED**")
        self.assertEqual(
            signals["metadata"]["nested"][0]["password"], "**REDACTED**"
        )


if __name__ == "__main__":
    unittest.main()
