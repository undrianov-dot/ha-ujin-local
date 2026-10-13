"""Pure protocol helpers for the local UJIN UDP protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from ipaddress import IPv4Address
from typing import Any


@dataclass(slots=True)
class ParsedPacket:
    """Normalized UJIN packet."""

    serial: int
    model: str
    token: str | None
    signals: dict[str, Any]
    unique_id: int | str | None = None


def is_recent(
    last_seen: datetime,
    now: datetime | None = None,
    timeout: timedelta = timedelta(minutes=5),
) -> bool:
    """Return whether a device timestamp is within the availability window."""
    if last_seen.tzinfo is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return False
    return current - last_seen <= timeout


def _merge_data(value: Any) -> dict[str, Any]:
    """Merge the dict or list-of-dicts used by different firmware families."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        merged: dict[str, Any] = {}
        for item in value:
            if isinstance(item, dict):
                merged.update(item)
        return merged
    return {}


def _first_dict(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    """Return the first nested mapping used by known packet envelopes."""
    if not isinstance(value, dict):
        return {}
    for key in keys:
        nested = value.get(key)
        if isinstance(nested, dict):
            return nested
    return {}


def parse_packet(payload: bytes | str) -> ParsedPacket | None:
    """Parse legacy Sapfir and current UJIN packet envelopes."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="strict")
    payload = payload.strip().strip("\x00")
    if not payload or payload == "Discovery":
        return None

    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(decoded, dict):
        return None

    envelope = decoded.get("header", decoded)
    if not isinstance(envelope, dict):
        return None

    # A few firmware versions wrap the useful fields in a body/payload object.
    body = _first_dict(envelope, ("body", "payload", "message"))
    source = body or envelope
    serial_raw = source.get("id", envelope.get("id", decoded.get("id")))
    if serial_raw is None:
        return None
    try:
        serial = int(serial_raw)
    except (TypeError, ValueError):
        return None
    if serial < 0:
        return None

    model = str(
        source.get("devName")
        or source.get("dev_name")
        or source.get("model")
        or source.get("name")
        or source.get("type")
        or envelope.get("devName")
        or envelope.get("dev_name")
        or envelope.get("model")
        or decoded.get("devName")
        or "UJIN device"
    )
    signals = _merge_data(source.get("data"))
    if not signals:
        signals = _merge_data(envelope.get("data"))
    if not signals:
        signals = {
            key: value
            for key, value in source.items()
            if key
            not in {
                "id",
                "devName",
                "dev_name",
                "model",
                "name",
                "type",
                "token",
                "data",
            }
        }

    token_raw = source.get("token", envelope.get("token", decoded.get("token")))
    if token_raw in (None, ""):
        token_raw = signals.get("token")
    token = str(token_raw) if token_raw not in (None, "") else None

    unique_id = None
    for mapping in (source, envelope, decoded, signals):
        unique_id = mapping.get("uniq_id", mapping.get("unique_id"))
        if unique_id is not None:
            break

    # Some current firmware keeps protocol metadata at the envelope level.
    for key in ("uniq_id", "ver", "rssi", "time"):
        for mapping in (source, envelope, decoded):
            if key in mapping and key not in signals:
                signals[key] = mapping[key]

    return ParsedPacket(
        serial=serial,
        model=model,
        token=token,
        signals=signals,
        unique_id=unique_id,
    )


def build_management_command(
    serial: int,
    token: str,
    unique_id: int,
    changes: dict[str, Any],
) -> bytes:
    """Build a compact local-management command."""
    command: dict[str, Any] = {
        "command": "management",
        "id": serial,
        "uniq_id": unique_id,
        "token": token,
    }
    command.update(changes)
    return json.dumps(command, separators=(",", ":"), ensure_ascii=False).encode()


def value_is_on(value: Any) -> bool:
    """Interpret the common scalar encodings used by UJIN firmware."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "off", "closed", "no", "none", ""}:
            return False
        if normalized in {"1", "true", "on", "open", "yes"}:
            return True
    return bool(value)


def finite_number(value: Any) -> float | None:
    """Reject missing, boolean and non-finite sensor values."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def whole_degree(value: Any, minimum: float = 5, maximum: float = 40) -> int:
    """Validate before rounding; half degrees round up, not to even."""
    number = finite_number(value)
    if number is None or not minimum <= number <= maximum:
        raise ValueError(f"Temperature must be between {minimum} and {maximum} �C")
    target = math.floor(number + 0.5)
    if not minimum <= target <= maximum:
        raise ValueError("Rounded temperature is outside the device limits")
    return target


def command_endpoint(signals: dict[str, Any], source_ip: str, default_port: int) -> tuple[str, int]:
    """Use the device's LAN address when telemetry is forwarded by UJIN mesh.

    Never redirect commands to a public, multicast or unspecified address.
    The HA listening port is not necessarily the device management port.
    """
    address = source_ip
    try:
        candidate = IPv4Address(str(signals.get("ip", "")))
        if candidate.is_private and not (
            candidate.is_loopback or candidate.is_multicast or candidate.is_unspecified
            or str(candidate) == "255.255.255.255"
        ):
            address = str(candidate)
    except ValueError:
        pass
    port = finite_number(signals.get("udpp"))
    return address, int(port) if port is not None and port.is_integer() and 1 <= port <= 65535 else default_port

