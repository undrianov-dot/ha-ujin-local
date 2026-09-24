# Changelog

## 0.3.1

- Restore the complete constants module after the 0.3.0 packaging error.

## 0.3.0

- Enable target-temperature controls for Potato thermostats that only publish the current `term` value.
- Send the local `reg-term` management command when firmware does not advertise a writable setpoint signal.
- Keep the last acknowledged setpoint visible in Home Assistant.
