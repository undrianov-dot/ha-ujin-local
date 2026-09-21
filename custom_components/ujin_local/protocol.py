"""Pure protocol helpers for the local UJIN UDP protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
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

    unique_id = source.get("uniq_id", source.get("unique_id"))
    if unique_id is None:
        unique_id = signals.get("uniq_id", signals.get("unique_id"))

    # Some current firmware keeps protocol metadata at the envelope level.
    for key in ("uniq_id", "ver", "rssi", "time"):
        if key in source and key not in signals:
            signals[key] = source[key]

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
