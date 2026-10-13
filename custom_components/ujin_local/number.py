"""Validated thermostat configuration controls."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .climate import _has_thermostat_signals, _is_thermostat, async_set_setpoint
from .const import DOMAIN, SIGNAL_DEVICE_ADDED, SIGNAL_DEVICE_UPDATED, TARGET_TEMPERATURE_KEYS
from .entity import UjinEntity
from .hub import UjinHub
from .protocol import finite_number


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: UjinHub = hass.data[DOMAIN][entry.entry_id]
    entities: dict[tuple[int, str], NumberEntity] = {}

    @callback
    def sync_device(serial: int) -> None:
        device = hub.devices[serial]
        if not (_is_thermostat(device.model) or _has_thermostat_signals(device.signals)):
            return
        controls = [("setpoint", UjinSetpoint)]
        if "br-lcd" in device.signals:
            controls.append(("brightness", UjinBrightness))
        for key, factory in controls:
            identity = (serial, key)
            if identity not in entities:
                entities[identity] = factory(hub, serial)
                async_add_entities([entities[identity]])
            elif entities[identity].hass is not None:
                entities[identity].async_write_ha_state()

    for serial in hub.devices:
        sync_device(serial)
    for signal in (SIGNAL_DEVICE_ADDED, SIGNAL_DEVICE_UPDATED):
        entry.async_on_unload(async_dispatcher_connect(hass, signal, sync_device))


class UjinSetpoint(UjinEntity, NumberEntity):
    """Absolute entry works even before the first setpoint telemetry arrives."""

    _attr_name = "Temperature setpoint"
    _attr_icon = "mdi:thermometer-check"
    _attr_native_min_value = 5
    _attr_native_max_value = 40
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, hub: UjinHub, serial: int) -> None:
        super().__init__(hub, serial)
        self._attr_unique_id = f"{serial}_temperature_setpoint_number"

    @property
    def native_value(self) -> float | None:
        _, value = self.device.first_signal(TARGET_TEMPERATURE_KEYS)
        return finite_number(value)

    @property
    def available(self) -> bool:
        # Unknown current value must not prevent an explicit, owner-chosen target.
        return super().available and bool(self.device.token)

    async def async_set_native_value(self, value: float) -> None:
        await async_set_setpoint(self.hub, self.serial, value)
        self.async_write_ha_state()


class UjinBrightness(UjinEntity, NumberEntity):
    _attr_name = "Display brightness"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:brightness-6"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hub: UjinHub, serial: int) -> None:
        super().__init__(hub, serial)
        self._attr_unique_id = f"{serial}_br-lcd_number"

    @property
    def native_value(self) -> float | None:
        return finite_number(self.device.signals.get("br-lcd"))

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    async def async_set_native_value(self, value: float) -> None:
        number = finite_number(value)
        if number is None or not number.is_integer() or not 0 <= number <= 100:
            raise HomeAssistantError("Display brightness must be an integer from 0 to 100")
        await self.hub.async_send_changes(self.serial, {"br-lcd": int(number)})
        # Telemetry, not optimistic state, remains authoritative for settings.
