"""Diagnostic and measurement sensors for UJIN devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, METADATA_KEYS, SECRET_KEYS, SIGNAL_DEVICE_ADDED, SIGNAL_DEVICE_UPDATED
from .entity import UjinEntity
from .hub import UjinHub

_SKIP_VALUES = (dict, list, tuple, set)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: UjinHub = hass.data[DOMAIN][entry.entry_id]
    added: set[tuple[int, str]] = set()
    entities: dict[tuple[int, str], UjinSignalSensor] = {}

    @callback
    def sync_device(serial: int) -> None:
        device = hub.devices[serial]
        new_entities: list[UjinSignalSensor] = []
        for key, value in device.signals.items():
            identity = (serial, key)
            if (
                identity in added
                or key in METADATA_KEYS
                or key in SECRET_KEYS
                or isinstance(value, _SKIP_VALUES)
            ):
                continue
            entity = UjinSignalSensor(hub, serial, key)
            added.add(identity)
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


class UjinSignalSensor(UjinEntity, SensorEntity):
    def __init__(self, hub: UjinHub, serial: int, signal_name: str) -> None:
        super().__init__(hub, serial)
        self.signal_name = signal_name
        self._attr_unique_id = f"{serial}_{signal_name}"
        self._attr_name = signal_name.replace("-", " ").replace("_", " ").title()
        lower = signal_name.lower()
        if (
            lower
            in {
                "term",
                "temp",
                "temperature",
                "term-sex",
                "floor-temp",
                "floor_temperature",
                "reg-term",
                "treg",
                "target-temp",
                "target_temperature",
                "set-temp",
                "setpoint",
            }
            or "temperature" in lower
        ):
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif lower == "rssi":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif lower in {"hum", "humidity"}:
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> Any:
        return self.device.signals.get(self.signal_name)
