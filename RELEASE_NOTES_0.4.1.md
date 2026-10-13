# UJIN Local 0.4.1

## Changes

- Every thermostat has a Temperature setpoint number entity with a 1 degree
  Celsius step. Box mode allows the owner to enter an explicit target even
  when the initial setpoint has not yet been received. No room-temperature
  fallback or arbitrary initial setpoint is used.
- Climate and number controls send the same acknowledged, whole-degree
  command. The existing 5-40 degree range remains unchanged. Fractional service
  values are rounded to the nearest integer, with halves rounded up.
- Leak, valve, relay and input readings are now included in the restart cache.
  Critical changes are persisted immediately instead of waiting for the
  measurement-cache interval. Secret signals are still excluded.
- The leak controller has a separate diagnostic Connection binary sensor.
  A live heartbeat and an unknown valve/leak state can now be distinguished.
- Leak readings are unavailable after the device's heartbeat times out,
  rather than continuing to present a stale OK/alarm state.

## Limits and deployment

This release cannot reconstruct readings that were never received or were lost
before the fix was installed. The valve and leak readings remain unavailable
until their corresponding device signals arrive. They are not inferred from
an absence of alarms, nor from the mere presence of a network heartbeat.

Unit tests use simulated transports and HA interfaces. They verify persistence,
validation, unknown-value handling, synchronized targets and failed-command
behavior, but do not prove physical actuation. A real change still requires
the owner's separate permission and comparison with the thermostat display.

After installing in HACS, restart Home Assistant. Existing climate, relay and
leak entity identifiers are unchanged. New setpoint and connection entities
are additive. To roll back, select 0.4.0 in HACS, download and restart HA.
