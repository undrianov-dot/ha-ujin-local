"""Pure protocol helpers for the local UJIN UDP protocol."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(slots=True)
class ParsedPacket:
    """Normalized UJIN packet."""

    serial: int
    model: str
    token: str | None
    signals: dict[str, Any]


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


def parse_packet(payload: bytes | str) -> ParsedPacket | None:
    """Parse legacy Sapfir and current UJIN packet envelopes."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="strict")
    payload = payload.strip().strip("\x00")
    if not payload or payload == "Discovery":
        return None

    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        return None

    envelope = decoded.get("header", decoded)
    if not isinstance(envelope, dict):
        return None

    serial_raw = envelope.get("id", decoded.get("id"))
    if serial_raw is None:
        return None
    serial = int(serial_raw)

    model = str(
        envelope.get("devName")
        or envelope.get("dev_name")
        or envelope.get("model")
        or decoded.get("devName")
        or "UJIN device"
    )
    signals = _merge_data(envelope.get("data"))
    if not signals:
        signals = {
            key: value
            for key, value in envelope.items()
            if key not in {"id", "devName", "dev_name", "model", "token", "data"}
        }

    token_raw = envelope.get("token", decoded.get("token"))
    if token_raw in (None, ""):
        token_raw = signals.get("token")
    token = str(token_raw) if token_raw not in (None, "") else None

    # Some current firmware keeps protocol metadata at the envelope level.
    for key in ("uniq_id", "ver", "rssi", "time"):
        if key in envelope and key not in signals:
            signals[key] = envelope[key]

    return ParsedPacket(serial=serial, model=model, token=token, signals=signals)


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
