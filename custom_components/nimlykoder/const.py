"""Constants for the Nimlykoder integration."""

DOMAIN = "nimlykoder"

# Configuration keys
CONF_LOCK_ENTITY = "lock_entity"
CONF_SLOT_MIN = "slot_min"
CONF_SLOT_MAX = "slot_max"
CONF_RESERVED_SLOTS = "reserved_slots"
CONF_AUTO_EXPIRE = "auto_expire"
CONF_CLEANUP_TIME = "cleanup_time"
CONF_OVERWRITE_PROTECTION = "overwrite_protection"

# Legacy config key (for migration)
CONF_MQTT_TOPIC = "mqtt_topic"

# ZHA-specific config key: the endpoint on the lock device that exposes
# the ZCL Door Lock cluster (0x0101). For Nimly locks paired via ZHA this
# is endpoint 11 (per zigpy/zha-device-handlers#3095), not endpoint 1.
CONF_ZHA_ENDPOINT_ID = "zha_endpoint_id"
CONF_DOOR_SENSOR = "door_sensor"

# Defaults
# Slot 0 is never usable for a PIN code — ZCL DoorLock attribute reports use
# user_id/slot 0 to mean "no specific user" (manual/zigbee-initiated actions),
# so a real code living in slot 0 would make activity-log attribution ambiguous.
DEFAULT_SLOT_MIN = 1
DEFAULT_SLOT_MAX = 99
DEFAULT_RESERVED_SLOTS = [1, 2, 3]
DEFAULT_AUTO_EXPIRE = True
DEFAULT_CLEANUP_TIME = "03:00:00"
DEFAULT_OVERWRITE_PROTECTION = True
DEFAULT_ZHA_ENDPOINT_ID = 11

# Storage
STORAGE_VERSION = 1
STORAGE_KEY = "nimlykoder_codes"
ACTIVITY_STORAGE_KEY = "nimlykoder_activity"
ACTIVITY_STORAGE_VERSION = 1
ACTIVITY_LOG_MAX = 200

# Raw ZCL DoorLock attribute-report log — kept separately from the (decoded)
# activity log so raw bytes can be diffed against sensor.<lock>_last_pin_code
# to verify which byte-layout interpretation (old vs new) is correct.
RAW_PING_STORAGE_KEY = "nimlykoder_raw_pings"
RAW_PING_STORAGE_VERSION = 1
RAW_PING_LOG_MAX = 1000

# Event fired on the HA bus for a failed (wrong) PIN attempt. Deliberately
# carries no slot/user/name — automations can react to it without exposing
# which code was guessed.
EVENT_WRONG_PIN_ATTEMPT = "nimlykoder_wrong_pin_attempt"

# Entry types
TYPE_PERMANENT = "permanent"
TYPE_GUEST = "guest"

# Services
SERVICE_SET_AUTO_LOCK = "set_auto_lock"
SERVICE_ADD_CODE = "add_code"
SERVICE_REMOVE_CODE = "remove_code"
SERVICE_UPDATE_EXPIRY = "update_expiry"
SERVICE_UPDATE_NAME = "update_name"
SERVICE_UPDATE_PIN = "update_pin"
SERVICE_LIST_CODES = "list_codes"
SERVICE_CLEANUP_EXPIRED = "cleanup_expired"

# WebSocket commands
WS_TYPE_LIST = "nimlykoder/list"
WS_TYPE_ADD = "nimlykoder/add"
WS_TYPE_REMOVE = "nimlykoder/remove"
WS_TYPE_UPDATE_EXPIRY = "nimlykoder/update_expiry"
WS_TYPE_UPDATE_NAME = "nimlykoder/update_name"
WS_TYPE_UPDATE_PIN = "nimlykoder/update_pin"
WS_TYPE_SUGGEST_SLOTS = "nimlykoder/suggest_slots"
WS_TYPE_CONFIG = "nimlykoder/config"
WS_TYPE_TRANSLATIONS = "nimlykoder/translations"
WS_TYPE_SET_AUTO_LOCK = "nimlykoder/set_auto_lock"
WS_TYPE_ACTIVITY = "nimlykoder/activity"
WS_TYPE_GET_LOCK_SETTINGS = "nimlykoder/get_lock_settings"
WS_TYPE_SET_LOCK_SETTING = "nimlykoder/set_lock_setting"

# Auto-lock options (stored in nimlykoder config entry options)
OPT_AUTO_LOCK_ENABLED = "auto_lock_enabled"
OPT_AUTO_LOCK_DELAY = "auto_lock_delay"

# Panel
PANEL_NAME = "nimlykoder"
PANEL_TITLE = "Nimlykoder"
PANEL_ICON = "mdi:door-closed-lock"
PANEL_URL = "/api/panel_custom/nimlykoder"
