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
    entities: dict[int, UjinValveSwitch] = {}

    @callback
    def sync_device(serial: int) -> None:
        device = hub.devices[serial]
        is_leak_controller = any(marker in device.model.lower() for marker in LEAK_MODEL_MARKERS)
        signal_name, _ = device.first_signal(VALVE_KEYS)
        if is_leak_controller and signal_name and serial not in entities:
            entity = UjinValveSwitch(hub, serial, signal_name)
            entities[serial] = entity
            async_add_entities([entity])
        if serial in entities and entities[serial].hass is not None:
            entities[serial].async_write_ha_state()

    for serial in list(hub.devices):
        sync_device(serial)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, sync_device))
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATED, sync_device))


class UjinValveSwitch(UjinEntity, SwitchEntity):
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_name = "Water valve"

    def __init__(self, hub: UjinHub, serial: int, signal_name: str) -> None:
        super().__init__(hub, serial)
        self.signal_name = signal_name
        self._attr_unique_id = f"{serial}_{signal_name}_switch"

    @property
    def is_on(self) -> bool:
        return value_is_on(self.device.signals.get(self.signal_name))

    async def async_turn_on(self, **kwargs) -> None:
        self.hub.send_changes(self.serial, {self.signal_name: 1})

    async def async_turn_off(self, **kwargs) -> None:
        self.hub.send_changes(self.serial, {self.signal_name: 0})
