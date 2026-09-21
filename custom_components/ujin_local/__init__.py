"""UJIN Local integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryDisabler

from .const import CURATED_SENSOR_KEYS, DEFAULT_PORT, DOMAIN, PLATFORMS
from .hub import UjinHub


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _disable_legacy_raw_sensors(hass, entry)
    hub = UjinHub(hass, entry, entry.data.get("port", DEFAULT_PORT))
    await hub.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _disable_legacy_raw_sensors(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Disable noisy v0.1 raw sensors while preserving useful measurements."""
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain != "sensor" or "_" not in entity.unique_id:
            continue
        _, signal_name = entity.unique_id.split("_", 1)
        if signal_name not in CURATED_SENSOR_KEYS and entity.disabled_by is None:
            registry.async_update_entity(
                entity.entity_id, disabled_by=RegistryEntryDisabler.INTEGRATION
            )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hub: UjinHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.async_stop()
    return unloaded
