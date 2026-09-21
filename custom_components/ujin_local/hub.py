"""UDP hub for UJIN Local."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import socket
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_DEVICE_ADDED, SIGNAL_DEVICE_UPDATED
from .protocol import ParsedPacket, build_management_command, parse_packet

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class UjinDevice:
    """Runtime state of one local UJIN device."""

    serial: int
    model: str
    ip_address: str
    token: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def first_signal(self, keys: tuple[str, ...]) -> tuple[str | None, Any]:
        for key in keys:
            if key in self.signals:
                return key, self.signals[key]
        return None, None


class _UjinDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, hub: "UjinHub") -> None:
        self.hub = hub

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.hub.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.hub.handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("UJIN UDP error: %s", exc)


class UjinHub:
    """Listen for UJIN broadcasts and send local management commands."""

    def __init__(self, hass: HomeAssistant, port: int) -> None:
        self.hass = hass
        self.port = port
        self.transport: asyncio.DatagramTransport | None = None
        self.devices: dict[int, UjinDevice] = {}

    async def async_start(self) -> None:
        loop = asyncio.get_running_loop()

        def make_socket() -> socket.socket:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_socket.setblocking(False)
            udp_socket.bind(("0.0.0.0", self.port))
            return udp_socket

        udp_socket = make_socket()
        await loop.create_datagram_endpoint(
            lambda: _UjinDatagramProtocol(self),
            sock=udp_socket,
        )
        _LOGGER.info("Listening for UJIN devices on UDP port %s", self.port)

    async def async_stop(self) -> None:
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    def handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            packet = parse_packet(data)
        except (UnicodeDecodeError, ValueError, TypeError):
            _LOGGER.debug("Ignored malformed UJIN packet from %s", addr[0])
            return
        if packet is None:
            return
        self._update_device(packet, addr[0])

    def _update_device(self, packet: ParsedPacket, ip_address: str) -> None:
        is_new = packet.serial not in self.devices
        if is_new:
            device = UjinDevice(packet.serial, packet.model, ip_address)
            self.devices[packet.serial] = device
        else:
            device = self.devices[packet.serial]

        if packet.model != "UJIN device":
            device.model = packet.model
        device.ip_address = ip_address
        device.token = packet.token or device.token
        device.signals.update(packet.signals)
        device.last_seen = datetime.now(timezone.utc)

        signal = SIGNAL_DEVICE_ADDED if is_new else SIGNAL_DEVICE_UPDATED
        async_dispatcher_send(self.hass, signal, packet.serial)

    def send_changes(self, serial: int, changes: dict[str, Any]) -> None:
        device = self.devices[serial]
        if self.transport is None:
            raise RuntimeError("UJIN UDP listener is not running")
        if not device.token:
            raise RuntimeError(f"Token for UJIN device {serial} has not been received")
        unique_id = int(time.time_ns() // 1_000_000 % 100_000_000)
        payload = build_management_command(serial, device.token, unique_id, changes)
        self.transport.sendto(payload, (device.ip_address, self.port))
        _LOGGER.debug("Sent UJIN command to %s: keys=%s", serial, list(changes))
