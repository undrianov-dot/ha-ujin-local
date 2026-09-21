"""Leak binary sensors for UJIN devices."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LEAK_KEYS, SIGNAL_DEVICE_ADDED, SIGNAL_DEVICE_UPDATED
from .entity import UjinEntity
from .hub import UjinHub
from .protocol import value_is_on


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: UjinHub = hass.data[DOMAIN][entry.entry_id]
    entities: dict[tuple[int, str], UjinLeakSensor] = {}

    @callback
    def sync_device(serial: int) -> None:
        new_entities = []
        for key in LEAK_KEYS:
            identity = (serial, key)
            if key in hub.devices[serial].signals and identity not in entities:
                entity = UjinLeakSensor(hub, serial, key)
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


class UjinLeakSensor(UjinEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_name = "Leak"

    def __init__(self, hub: UjinHub, serial: int, signal_name: str) -> None:
        super().__init__(hub, serial)
        self.signal_name = signal_name
        self._attr_unique_id = f"{serial}_{signal_name}_binary"

    @property
    def is_on(self) -> bool:
        return value_is_on(self.device.signals.get(self.signal_name))
