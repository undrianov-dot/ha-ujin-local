# Changelog

## 0.1.0

- First experimental release.
- Local UDP discovery on port `30300`.
- Climate entities for UJIN thermostats.
- Leak binary sensors and conditional valve switches.
- Generic sensors for unknown scalar signals.
- Diagnostics with secret-field redaction.
- More tolerant parsing of nested and incomplete UDP envelopes.
- Thermostat discovery from temperature fields and relay-controller support
  for `dinrelay` models.
- Entity availability now follows a five-minute UDP timeout and exposes the
  timezone-aware `last_seen` attribute.
- Device connection details persist in config-entry storage, and thermostat
  setpoint commands require a matching `uniq_id` acknowledgement.
