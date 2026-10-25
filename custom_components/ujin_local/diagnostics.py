"""Diagnostics for UJIN Local."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, SECRET_KEYS
from .hub import UjinHub


def _redact_sensitive_data(value: Any) -> Any:
    """Redact secret fields, including those nested in packet values."""
    if isinstance(value, dict):
        return {
            key: (
                "**REDACTED**"
                if str(key).lower() in SECRET_KEYS
                else _redact_sensitive_data(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_data(item) for item in value]
    return value


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
                "management_port": device.management_port,
                "token_received": bool(device.token),
                "last_seen": device.last_seen.isoformat(),
                "signals": _redact_sensitive_data(device.signals),
            }
            for serial, device in hub.devices.items()
        },
    }
