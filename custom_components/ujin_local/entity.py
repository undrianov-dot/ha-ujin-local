"""Shared UJIN entity base."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, DEVICE_TIMEOUT
from .hub import UjinDevice, UjinHub
from .protocol import is_recent


class UjinEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: UjinHub, serial: int) -> None:
        self.hub = hub
        self.serial = serial

    @property
    def device(self) -> UjinDevice:
        return self.hub.devices[self.serial]

    @property
    def available(self) -> bool:
        return is_recent(self.device.last_seen, timeout=DEVICE_TIMEOUT)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "last_seen": self.device.last_seen.isoformat(),
            "ip_address": self.device.ip_address,
            "management_port": self.device.management_port,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, str(self.serial))},
            manufacturer="UJIN",
            model=self.device.model,
            name=f"UJIN {self.serial}",
            sw_version=str(self.device.signals.get("ver", "")) or None,
            configuration_url=f"http://{self.device.ip_address}/",
        )

