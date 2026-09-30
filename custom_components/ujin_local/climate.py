"""Climate entities for UJIN thermostats."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CURRENT_TEMPERATURE_KEYS,
    DEFAULT_TARGET_TEMPERATURE_KEY,
    DOMAIN,
    HEAT_RELAY_KEYS,
    SIGNAL_DEVICE_ADDED,
    SIGNAL_DEVICE_UPDATED,
    TARGET_TEMPERATURE_KEYS,
    THERMOSTAT_MODEL_MARKERS,
    WRITABLE_TARGET_TEMPERATURE_KEYS,
)
from .entity import UjinEntity
from .hub import UjinHub
from .protocol import finite_number, value_is_on, whole_degree


def _is_thermostat(model: str) -> bool:
    lower = model.lower()
    return any(marker in lower for marker in THERMOSTAT_MODEL_MARKERS)


def _has_thermostat_signals(signals: dict[str, Any]) -> bool:
    keys = {key.lower() for key in signals}
    return bool(keys & set(CURRENT_TEMPERATURE_KEYS + TARGET_TEMPERATURE_KEYS))


async def async_set_setpoint(hub: UjinHub, serial: int, temperature: Any) -> None:
    """Shared, acknowledged whole-degree command for climate and number controls."""
    device = hub.devices[serial]
    signal_name, _ = device.first_signal(WRITABLE_TARGET_TEMPERATURE_KEYS)
    if signal_name is None:
        signal_name = (
            "treg" if "potato-trm" in device.model.lower()
            else DEFAULT_TARGET_TEMPERATURE_KEY
        )
    try:
        target = whole_degree(temperature, 5, 40)
    except ValueError as err:
        raise HomeAssistantError(str(err)) from err
    await hub.async_send_changes(serial, {signal_name: target})
    device.signals[signal_name] = target
    hub._persist_device(device)
    async_dispatcher_send(hub.hass, SIGNAL_DEVICE_UPDATED, serial)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: UjinHub = hass.data[DOMAIN][entry.entry_id]
    entities: dict[int, UjinThermostat] = {}

    @callback
    def add_device(serial: int) -> None:
        device = hub.devices[serial]
        if serial not in entities and (
            _is_thermostat(device.model) or _has_thermostat_signals(device.signals)
        ):
            entity = UjinThermostat(hub, serial)
            entities[serial] = entity
            async_add_entities([entity])

    @callback
    def update_device(serial: int) -> None:
        add_device(serial)
        if serial in entities and entities[serial].hass is not None:
            entities[serial].async_write_ha_state()

    for serial in list(hub.devices):
        add_device(serial)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, add_device))
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATED, update_device))


class UjinThermostat(UjinEntity, ClimateEntity):
    _attr_name = "Thermostat"
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = 5
    _attr_max_temp = 40

    def __init__(self, hub: UjinHub, serial: int) -> None:
        super().__init__(hub, serial)
        self._attr_unique_id = f"{serial}_climate"

    @property
    def current_temperature(self) -> float | None:
        _, value = self.device.first_signal(CURRENT_TEMPERATURE_KEYS)
        return finite_number(value)

    @property
    def current_humidity(self) -> float | None:
        return finite_number(self.device.signals.get("hum"))

    @property
    def target_temperature(self) -> float | None:
        _, value = self.device.first_signal(TARGET_TEMPERATURE_KEYS)
        # A measured temperature is not a setpoint. Wait for real telemetry.
        return finite_number(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            **super().extra_state_attributes,
            "floor_temperature": finite_number(self.device.signals.get("term-sex")),
            "regulation_type_code": self.device.signals.get("treg-type"),
            "regulation_status_code": self.device.signals.get("treg-err"),
        }

    @property
    def supported_features(self) -> ClimateEntityFeature:
        return ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def hvac_action(self) -> HVACAction | None:
        signal_name, value = self.device.first_signal(HEAT_RELAY_KEYS)
        if signal_name is None:
            return None
        return HVACAction.HEATING if value_is_on(value) else HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await async_set_setpoint(self.hub, self.serial, temperature)
        self.async_write_ha_state()
