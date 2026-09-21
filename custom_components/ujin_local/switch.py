"""Valve switch for UJIN leak controllers."""

from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    LEAK_MODEL_MARKERS,
    RELAY_KEYS,
    RELAY_MODEL_MARKERS,
    SIGNAL_DEVICE_ADDED,
    SIGNAL_DEVICE_UPDATED,
    VALVE_KEYS,
)
from .entity import UjinEntity
from .hub import UjinHub
from .protocol import value_is_on


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
        self._attr_device_class = (
            SwitchDeviceClass.OUTLET if not is_valve else SwitchDeviceClass.SWITCH
        )

    @property
    def is_on(self) -> bool:
        return value_is_on(self.device.signals.get(self.signal_name))

    async def async_turn_on(self, **kwargs) -> None:
        await self.hub.async_send_changes(self.serial, {self.signal_name: 1})

    async def async_turn_off(self, **kwargs) -> None:
        await self.hub.async_send_changes(self.serial, {self.signal_name: 0})
