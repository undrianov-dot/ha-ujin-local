"""Diagnostics for UJIN Local."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, SECRET_KEYS
from .hub import UjinHub


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    hub: UjinHub = hass.data[DOMAIN][entry.entry_id]
    return {
        "listen_port": hub.port,
        "devices": {
            str(serial): {
                "model": device.model,
                "ip_address": device.ip_address,
                "token_received": bool(device.token),
                "last_seen": device.last_seen.isoformat(),
                "signals": {
                    key: value
                    for key, value in device.signals.items()
                    if key not in SECRET_KEYS
                },
            }
            for serial, device in hub.devices.items()
        },
    }
