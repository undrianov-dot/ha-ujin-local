"""Constants for UJIN Local."""

from datetime import timedelta

DOMAIN = "ujin_local"
DEFAULT_PORT = 30300
DEVICE_TIMEOUT = timedelta(minutes=5)
AVAILABILITY_REFRESH_INTERVAL = timedelta(seconds=30)
COMMAND_ACK_TIMEOUT = timedelta(seconds=5)
PERSISTED_DEVICES_KEY = "devices"
PLATFORMS = ["binary_sensor", "climate", "sensor", "switch"]

SIGNAL_DEVICE_ADDED = f"{DOMAIN}_device_added"
SIGNAL_DEVICE_UPDATED = f"{DOMAIN}_device_updated"

THERMOSTAT_MODEL_MARKERS = ("trm", "termostat", "thermostat")
LEAK_MODEL_MARKERS = ("-ld-", "waterleak", "aqua")
RELAY_MODEL_MARKERS = ("dinrelay", "din-relay")

TARGET_TEMPERATURE_KEYS = (
    "reg-term",
    "treg",
    "target-temp",
    "target_temperature",
    "set-temp",
    "setpoint",
)
WRITABLE_TARGET_TEMPERATURE_KEYS = TARGET_TEMPERATURE_KEYS
CURRENT_TEMPERATURE_KEYS = (
    "term",
    "temperature",
    "temp",
    "air-temp",
    "t-air",
)
FLOOR_TEMPERATURE_KEYS = ("term-sex", "floor-temp", "floor_temperature")
HEAT_RELAY_KEYS = ("rele-wt", "rele-t", "heat", "heating")

LEAK_KEYS = (
    "leak",
    "water-leak",
    "water_leak",
    "leak-alarm",
    "leak_alarm",
    "alarm",
    "ld",
)
VALVE_KEYS = ("rele-w", "water-valve", "water_valve", "valve", "rele1")
RELAY_KEYS = ("rele1", "rele2")
RELAY_INPUT_KEYS = ("in1", "in2")

THERMOSTAT_SENSOR_KEYS = ("co2", "air-iaq", "lux", "rssi")
RELAY_SENSOR_KEYS = ("rssi",)
CURATED_SENSOR_KEYS = frozenset((*THERMOSTAT_SENSOR_KEYS, *RELAY_SENSOR_KEYS))

SECRET_KEYS = {
    "token",
    "password",
    "psw",
    "ssid",
    "mesh_info",
}

METADATA_KEYS = {
    "id",
    "devName",
    "dev_name",
    "model",
    "uniq_id",
    "sn",
    *SECRET_KEYS,
}
