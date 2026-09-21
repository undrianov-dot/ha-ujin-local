"""Stable measurement sensors for UJIN devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfRatio,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .climate import _is_thermostat
from .const import (
    DOMAIN,
    RELAY_MODEL_MARKERS,
    RELAY_SENSOR_KEYS,
    SIGNAL_DEVICE_ADDED,
    SIGNAL_DEVICE_UPDATED,
    THERMOSTAT_SENSOR_KEYS,
)
from .entity import UjinEntity
from .hub import UjinHub


@dataclass(frozen=True, slots=True)
class UjinSensorDescription:
    name: str
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    diagnostic: bool = False


SENSOR_DESCRIPTIONS = {
    "co2": UjinSensorDescription(
        "Carbon dioxide", SensorDeviceClass.CO2, UnitOfRatio.PARTS_PER_MILLION
    ),
    "air-iaq": UjinSensorDescription("Indoor air quality"),
    "lux": UjinSensorDescription(
        "Illuminance", SensorDeviceClass.ILLUMINANCE, LIGHT_LUX
    ),
    "rssi": UjinSensorDescription(
        "Signal strength",
        SensorDeviceClass.SIGNAL_STRENGTH,
        SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        True,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: UjinHub = hass.data[DOMAIN][entry.entry_id]
    entities: dict[tuple[int, str], UjinSignalSensor] = {}

    @callback
    def sync_device(serial: int) -> None:
        device = hub.devices[serial]
        lower_model = device.model.lower()
        keys: tuple[str, ...] = ()
        if _is_thermostat(device.model):
            keys = THERMOSTAT_SENSOR_KEYS
        elif any(marker in lower_model for marker in RELAY_MODEL_MARKERS):
            keys = RELAY_SENSOR_KEYS

        new_entities: list[UjinSignalSensor] = []
        for key in keys:
            identity = (serial, key)
            if identity in entities:
                continue
            entity = UjinSignalSensor(hub, serial, key)
            entities[identity] = entity
            new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)
        for (entity_serial, _), entity in entities.items():
            if entity_serial == serial and entity.hass is not None:
                entity.async_write_ha_state()

    for serial in list(hub.devices):
        sync_device(serial)
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, sync_device)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATED, sync_device)
    )


class UjinSignalSensor(UjinEntity, SensorEntity):
    def __init__(self, hub: UjinHub, serial: int, signal_name: str) -> None:
        super().__init__(hub, serial)
        self.signal_name = signal_name
        self._attr_unique_id = f"{serial}_{signal_name}"
        description = SENSOR_DESCRIPTIONS[signal_name]
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.unit
        if description.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> Any:
        return self.device.signals.get(self.signal_name)

    @property
    def available(self) -> bool:
        return super().available and self.signal_name in self.device.signals
