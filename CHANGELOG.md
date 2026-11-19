# Changelog

## 0.4.2

- Add the native Potato thermostat relay-inversion configuration switch, only
  when the exact `rele-inv` signal is received. Unknown or stale settings cannot
  be written; discovery never sends commands. Persist reported inversion values
  across restarts without optimistically changing state after a command ACK.
- Keep known entity values available during UDP outages; the leak controller's
  separate connection entity still reports whether its heartbeat is recent.
- Throttle persistence of `last_seen` updates to five minutes while saving
  device metadata and critical signal changes immediately.
- Recursively redact nested secret fields in diagnostics.
- Always clear and cancel pending command futures after send errors or cancellation.

## 0.4.1

- Persist leak, water-valve, relay and input states across restarts. Critical
  state changes bypass the normal 30-second measurement persistence throttle.
- Add a separate controller connection indicator. Receiving a heartbeat no
  longer has to be confused with receiving the valve/leak state.
- Add an absolute temperature-setpoint number control to every thermostat,
  with a 1 degree Celsius step and the existing 5-40 degree safety range.
- Share the acknowledged setpoint command between climate and number controls;
  failed commands do not change the displayed or persisted target.
- Mark cached leak readings unavailable when the device heartbeat expires.

## 0.3.1

- Restore the complete constants module after the 0.3.0 packaging error.

## 0.3.0

- Enable target-temperature controls for Potato thermostats that only publish the current `term` value.
- Send the local `reg-term` management command when firmware does not advertise a writable setpoint signal.
- Keep the last acknowledged setpoint visible in Home Assistant.
