# Changelog

## 0.2.0

- Stable entity set for thermostats, the DIN relay, and the leak controller.
- Automatically disable noisy raw sensors created by version 0.1.
- Add two switches and two binary inputs for `dinrelay_m4`.
- Require devices to advertise a setpoint field before enabling temperature control.
- Require a matching `uniq_id` acknowledgement for control commands.
- Persist device connection details and refresh availability every 30 seconds.
- Improve parsing of nested and incomplete UDP envelopes.
- Fix the Russian README encoding.

## 0.1.0

- First experimental release.
- Local UDP discovery on port `30300`.
- Climate entities, leak sensors, generic signal sensors, and diagnostics.
