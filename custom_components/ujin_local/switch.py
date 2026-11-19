"""Output switches and device configuration for UJIN devices."""

from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    DEVICE_TIMEOUT,
    LEAK_MODEL_MARKERS,
    RELAY_KEYS,
    RELAY_MODEL_MARKERS,
    SIGNAL_DEVICE_ADDED,
    SIGNAL_DEVICE_UPDATED,
    VALVE_KEYS,
    THERMOSTAT_RELAY_INVERSION_KEY,
)
from .entity import UjinEntity
from .hub import UjinHub
from .protocol import is_recent, value_is_on
from .climate import _is_thermostat


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: UjinHub = hass.data[DOMAIN][entry.entry_id]
    entities: dict[tuple[int, str], UjinSignalSwitch] = {}

    @callback
    def sync_device(serial: int) -> None:
        device = hub.devices[serial]
        is_leak_controller = any(
            marker in device.model.lower() for marker in LEAK_MODEL_MARKERS
        )
        is_relay = any(marker in device.model.lower() for marker in RELAY_MODEL_MARKERS)
        requested: list[tuple[str, str, bool]] = []
        if _is_thermostat(device.model) and "kid-bl" in device.signals:
            requested.append(("kid-bl", "Child lock", False))
        if is_relay:
            requested.extend(
                (key, f"Relay {index}", False)
                for index, key in enumerate(RELAY_KEYS, 1)
            )
        if is_leak_controller:
            signal_name, _ = device.first_signal(VALVE_KEYS)
            if signal_name:
                requested.append((signal_name, "Water valve", True))
        new_entities = []
        inversion_key = THERMOSTAT_RELAY_INVERSION_KEY
        if _is_thermostat(device.model) and inversion_key in device.signals:
            identity = (serial, inversion_key)
            if identity not in entities:
                entity = UjinRelayInversionSwitch(hub, serial)
                entities[identity] = entity
                new_entities.append(entity)
        for signal_name, name, is_valve in requested:
            identity = (serial, signal_name)
            if identity not in entities:
                entity = UjinSignalSwitch(hub, serial, signal_name, name, is_valve)
                entities[identity] = entity
                new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)
        for (entity_serial, _), entity in entities.items():
            if entity_serial == serial and entity.hass is not None:
                entity.async_write_ha_state()

    for serial in list(hub.devices):
        sync_device(serial)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, sync_device))
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATED, sync_device))


class UjinSignalSwitch(UjinEntity, SwitchEntity):
    def __init__(
        self, hub: UjinHub, serial: int, signal_name: str, name: str, is_valve: bool
    ) -> None:
        super().__init__(hub, serial)
        self.signal_name = signal_name
        self.is_valve = is_valve
        self._attr_unique_id = f"{serial}_{signal_name}_switch"
        self._attr_name = name
        if signal_name == "kid-bl":
            self._attr_entity_category = EntityCategory.CONFIG
            self._attr_icon = "mdi:lock"
        self._attr_device_class = (
            SwitchDeviceClass.SWITCH
        )

    @property
    def is_on(self) -> bool:
        return value_is_on(self.device.signals.get(self.signal_name))

    @property
    def available(self) -> bool:
        return super().available and self.signal_name in self.device.signals

    async def async_turn_on(self, **kwargs) -> None:
        await self.hub.async_send_changes(self.serial, {self.signal_name: 1})

    async def async_turn_off(self, **kwargs) -> None:
        await self.hub.async_send_changes(self.serial, {self.signal_name: 0})


class UjinRelayInversionSwitch(UjinSignalSwitch):
    """Native Potato relay polarity, discovered only from actual telemetry.

    This does not invert the displayed heating state or drive the relay directly.
    Do not assume older rele1-inv/rele2-inv fields are aliases of this setting.
    """

    def __init__(self, hub: UjinHub, serial: int) -> None:
        super().__init__(
            hub, serial, THERMOSTAT_RELAY_INVERSION_KEY, "Relay inversion", False
        )
        self._attr_name = None
        self._attr_translation_key = "relay_inversion"
        self._attr_entity_category = EntityCategory.CONFIG
        # Service-level setting: explicitly enable it only on the owner's
        # selected thermostat (currently the kitchen), not on all devices.
        self._attr_entity_registry_enabled_default = False
        self._attr_icon = "mdi:swap-horizontal"

    @property
    def is_on(self) -> bool | None:
        value = self.device.signals.get(self.signal_name)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str) and value.strip().lower() in (
            "0", "1", "true", "false", "on", "off"
        ):
            return value_is_on(value)
        return None

    @property
    def available(self) -> bool:
        return (
            super().available
            and bool(self.device.token)
            and is_recent(self.device.last_seen, timeout=DEVICE_TIMEOUT)
            and self.is_on is not None
        )

    async def _async_set_inversion(self, value: int) -> None:
        if not self.available:
            raise HomeAssistantError("Relay inversion is unavailable")
        # The hub waits for a matching command ACK. Displayed state changes only
        # when device telemetry reports the setting; no optimistic assignment.
        await self.hub.async_send_changes(self.serial, {self.signal_name: value})

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_inversion(1)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_inversion(0)

