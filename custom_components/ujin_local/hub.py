"""UDP hub for UJIN Local."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import socket
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    AVAILABILITY_REFRESH_INTERVAL,
    COMMAND_ACK_TIMEOUT,
    DEVICE_TIMEOUT,
    PERSISTENCE_INTERVAL,
    PERSISTED_DEVICES_KEY,
    SIGNAL_DEVICE_ADDED,
    SIGNAL_DEVICE_UPDATED,
)
from .protocol import ParsedPacket, build_management_command, is_recent, parse_packet

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
    last_available: bool | None = None

    def first_signal(self, keys: tuple[str, ...]) -> tuple[str | None, Any]:
        for key in keys:
            if key in self.signals:
                return key, self.signals[key]
        normalized = {signal.lower(): signal for signal in self.signals}
        for key in keys:
            signal = normalized.get(key.lower())
            if signal is not None:
                return signal, self.signals[signal]
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

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, port: int) -> None:
        self.hass = hass
        self.entry = entry
        self.port = port
        self.transport: asyncio.DatagramTransport | None = None
        self.devices: dict[int, UjinDevice] = {}
        self._availability_unsub: Any = None
        self._pending_commands: dict[int, tuple[int, asyncio.Future[bool]]] = {}
        self._persisted_devices: dict[int, tuple[str, str, str, datetime]] = {}
        self._restore_devices()

    def _restore_devices(self) -> None:
        persisted = self.entry.data.get(PERSISTED_DEVICES_KEY, {})
        if not isinstance(persisted, dict):
            return
        for serial_raw, stored in persisted.items():
            if not isinstance(stored, dict):
                continue
            try:
                serial = int(serial_raw)
            except (TypeError, ValueError):
                continue
            last_seen_raw = stored.get("last_seen")
            try:
                last_seen = datetime.fromisoformat(last_seen_raw)
            except (TypeError, ValueError):
                last_seen = datetime.now(timezone.utc)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            device = UjinDevice(
                serial=serial,
                model=str(stored.get("model") or "UJIN device"),
                ip_address=str(stored.get("ip_address") or ""),
                token=str(stored["token"]) if stored.get("token") else None,
                last_seen=last_seen,
            )
            self.devices[serial] = device
            self._persisted_devices[serial] = (
                device.model,
                device.ip_address,
                device.token or "",
                device.last_seen,
            )

    def _persist_device(self, device: UjinDevice) -> None:
        metadata = (device.model, device.ip_address, device.token or "")
        previous = self._persisted_devices.get(device.serial)
        if (
            previous is not None
            and previous[:3] == metadata
            and device.last_seen - previous[3] < PERSISTENCE_INTERVAL
        ):
            return
        persisted = {
            str(serial): {
                "model": item.model,
                "ip_address": item.ip_address,
                "token": item.token,
                "last_seen": item.last_seen.isoformat(),
            }
            for serial, item in self.devices.items()
        }
        data = dict(self.entry.data)
        data[PERSISTED_DEVICES_KEY] = persisted
        self.hass.config_entries.async_update_entry(self.entry, data=data)
        self._persisted_devices[device.serial] = (*metadata, device.last_seen)

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
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _UjinDatagramProtocol(self),
            sock=udp_socket,
        )
        # connection_made normally assigns this; keep the returned transport
        # as a fallback for event-loop implementations that call it later.
        if self.transport is None:
            self.transport = transport
        self._availability_unsub = async_track_time_interval(
            self.hass,
            self._async_refresh_availability,
            AVAILABILITY_REFRESH_INTERVAL,
        )
        _LOGGER.info("Listening for UJIN devices on UDP port %s", self.port)

    async def async_stop(self) -> None:
        if self._availability_unsub is not None:
            self._availability_unsub()
            self._availability_unsub = None
        if self.transport is not None:
            self.transport.close()
            self.transport = None
        for _, future in self._pending_commands.values():
            if not future.done():
                future.cancel()
        self._pending_commands.clear()

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
        device.last_available = True
        self._persist_device(device)

        pending = self._pending_commands.get(packet.serial)
        if pending is not None and str(packet.unique_id) == str(pending[0]):
            if not pending[1].done():
                pending[1].set_result(True)
            self._pending_commands.pop(packet.serial, None)

        signal = SIGNAL_DEVICE_ADDED if is_new else SIGNAL_DEVICE_UPDATED
        async_dispatcher_send(self.hass, signal, packet.serial)

    @callback
    def _async_refresh_availability(self, _now: datetime) -> None:
        """Refresh entities when a device crosses the availability timeout."""
        for serial, device in self.devices.items():
            available = is_recent(device.last_seen, timeout=DEVICE_TIMEOUT)
            if device.last_available != available:
                device.last_available = available
                async_dispatcher_send(self.hass, SIGNAL_DEVICE_UPDATED, serial)

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

    async def async_send_changes(
        self, serial: int, changes: dict[str, Any]
    ) -> None:
        device = self.devices[serial]
        if self.transport is None:
            raise HomeAssistantError("UJIN UDP listener is not running")
        if not device.token:
            raise HomeAssistantError(f"Token for UJIN device {serial} is unavailable")
        if serial in self._pending_commands:
            raise HomeAssistantError(
                f"Another UJIN command for device {serial} is awaiting acknowledgement"
            )
        unique_id = int(time.time_ns() // 1_000_000 % 100_000_000)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending_commands[serial] = (unique_id, future)
        payload = build_management_command(serial, device.token, unique_id, changes)
        self.transport.sendto(payload, (device.ip_address, self.port))
        try:
            await asyncio.wait_for(future, COMMAND_ACK_TIMEOUT.total_seconds())
        except asyncio.TimeoutError as err:
            self._pending_commands.pop(serial, None)
            _LOGGER.warning("No UJIN acknowledgement for command to %s", serial)
            raise HomeAssistantError(
                f"UJIN device {serial} did not acknowledge the command"
            ) from err
