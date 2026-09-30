# v0.4.0 - thermostat measurements and reliable local commands

- Thermostat setpoints use a 1 �C step in HA and outgoing commands. Fractional
  service calls are rounded to the nearest integer (half degrees round up).
  Validation occurs before rounding; the existing 5-40 �C safety range remains.
- Current Potato firmware's `treg` takes priority over legacy fallback fields.
  An unknown target is no longer replaced with the measured room temperature.
- Floor temperature, humidity, air pressure and noise measurements are exposed
  when advertised by the actual device, alongside air temperature, CO2, IAQ,
  illuminance and RSSI. Hardware variants without those sensors get no new
  placeholder entities.
- Display brightness and child-lock controls are provided as configuration
  entities. Commands still require device acknowledgement; telemetry remains
  authoritative for their state.
- Undocumented regulator enums, TVOC scale, hysteresis, PI interval, screen
  timeout and reported setting limits are exposed as raw diagnostic readings.
  No unverified mode labels or units are assigned to them.
- Device-reported private LAN IP and management port are respected when a
  mesh node forwards telemetry. Serial numbers above 2^31 remain unsigned.
- ACK identifiers are recognized at all supported envelope levels. Cancelled
  or failed sends no longer leave a thermostat blocked by a pending command.
- Curated readings are cached across HA restarts. Devices with no telemetry
  for five minutes become unavailable instead of looking permanently online.

## Verification and limitations

Unit tests use a simulated UDP transport and small HA interface doubles; they
are not proof of physical actuation. Check a real setpoint change separately
with the owner's permission, and compare the thermostat display and received
`treg` with HA. Serial ending in 204 is not special-cased: routing fixes apply
to every device, including mesh-enabled thermostat variants.

The firmware's schedule format, heating enable/disable command, regulator-type
codes and calibration scales have not been established. This release does not
guess those controls. HA automations can schedule the supported setpoint
service without relying on the UJIN cloud.

To roll back, select v0.3.1 in HACS, download and restart HA. Existing entity
IDs are preserved; new entities may remain as unavailable registry entries.

