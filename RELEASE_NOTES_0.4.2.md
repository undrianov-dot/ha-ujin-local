# UJIN Local 0.4.2

- Added a native **Relay inversion** configuration switch for Potato thermostats
  that publish `rele-inv`. The entity is disabled by default; enable it only for
  the thermostat you intend to configure. Installing does not apply inversion.
- The new setting rejects writes when the token, valid value or recent telemetry
  is missing. It displays device-reported state rather than an optimistic ACK.
- Reported inversion values survive restarts. Existing entity IDs are preserved.
- Includes the already merged reliability improvements: retained last-known
  values during UDP outages, throttled persistence, recursively redacted
  diagnostics and pending-command cleanup.

32 isolated protocol/runtime tests pass. Physical switching has not been tested
on installed heating equipment. Ensure safe conditions before using this setting.

Restart Home Assistant after updating the integration. To roll back, reinstall
0.4.1 and restart; do not remove the integration or its config entry.
