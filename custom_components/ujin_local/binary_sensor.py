"""Leak binary sensors for UJIN devices."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    LEAK_KEYS,
    LEAK_MODEL_MARKERS,
    RELAY_INPUT_KEYS,
    RELAY_MODEL_MARKERS,
    SIGNAL_DEVICE_ADDED,
    SIGNAL_DEVICE_UPDATED,
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
    entities: dict[tuple[int, str], UjinBinarySensor] = {}

    @callback
    def sync_device(serial: int) -> None:
        device = hub.devices[serial]
        lower_model = device.model.lower()
        requested: list[tuple[str, str, BinarySensorDeviceClass | None]] = []
        if any(marker in lower_model for marker in LEAK_MODEL_MARKERS):
            requested.append(("leak", "Leak", BinarySensorDeviceClass.MOISTURE))
        if any(marker in lower_model for marker in RELAY_MODEL_MARKERS):
            requested.extend(
                (key, f"Input {index}", None)
                for index, key in enumerate(RELAY_INPUT_KEYS, 1)
            )
        new_entities = []
        for key, name, device_class in requested:
            identity = (serial, key)
            if identity not in entities:
                entity = UjinBinarySensor(hub, serial, key, name, device_class)
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


class UjinBinarySensor(UjinEntity, BinarySensorEntity):
    def __init__(
        self,
        hub: UjinHub,
        serial: int,
        signal_name: str,
        name: str,
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        super().__init__(hub, serial)
        self.signal_name = signal_name
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_unique_id = f"{serial}_{signal_name}_binary"

    @property
    def is_on(self) -> bool | None:
        if self.signal_name == "leak":
            _, value = self.device.first_signal(LEAK_KEYS)
        else:
            value = self.device.signals.get(self.signal_name)
        if value is None:
            return None
        return value_is_on(value)

    @property
    def available(self) -> bool:
        if self.signal_name == "leak":
            signal_name, _ = self.device.first_signal(LEAK_KEYS)
            return super().available and signal_name is not None
        return super().available and self.signal_name in self.device.signals
