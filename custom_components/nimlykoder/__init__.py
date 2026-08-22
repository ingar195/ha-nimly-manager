"""The Nimlykoder integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

PLATFORMS = ["binary_sensor", "sensor"]
from homeassistant.helpers.event import async_track_time_change, async_track_state_change_event
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import ConfigEntryNotReady

from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    CONF_LOCK_ENTITY,
    CONF_MQTT_TOPIC,
    CONF_SLOT_MIN,
    CONF_SLOT_MAX,
    CONF_RESERVED_SLOTS,
    CONF_AUTO_EXPIRE,
    CONF_CLEANUP_TIME,
    CONF_OVERWRITE_PROTECTION,
    CONF_ZHA_ENDPOINT_ID,
    CONF_DOOR_SENSOR,
    DEFAULT_SLOT_MIN,
    DEFAULT_SLOT_MAX,
    DEFAULT_RESERVED_SLOTS,
    DEFAULT_AUTO_EXPIRE,
    DEFAULT_CLEANUP_TIME,
    DEFAULT_OVERWRITE_PROTECTION,
    DEFAULT_ZHA_ENDPOINT_ID,
    OPT_AUTO_LOCK_ENABLED,
    OPT_AUTO_LOCK_DELAY,
    ACTIVITY_STORAGE_KEY,
    ACTIVITY_STORAGE_VERSION,
    ACTIVITY_LOG_MAX,
    RAW_PING_STORAGE_KEY,
    RAW_PING_STORAGE_VERSION,
    RAW_PING_LOG_MAX,
    EVENT_WRONG_PIN_ATTEMPT,
)
from .storage import NimlykoderStorage
from .adapters.mqtt_z2m import MqttZ2mAdapter
from .adapters.zha_doorlock import ZhaDoorLockAdapter
from .services import async_setup_services, async_unload_services
from .websocket import async_register_websocket_handlers
from .panel import async_register_panel, async_unregister_panel
from .zha_helpers import get_doorlock_cluster

_LOGGER = logging.getLogger(__name__)


def _get_mqtt_topic_from_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    """Derive MQTT topic from a lock entity ID.
    
    For Zigbee2MQTT entities, we try to find the device's friendly name
    and construct the MQTT topic as: zigbee2mqtt/{friendly_name}
    """
    _LOGGER.info("[_get_mqtt_topic_from_entity] Deriving MQTT topic for entity: %s", entity_id)
    
    # Get the entity registry entry to find the device
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    
    if not entry:
        _LOGGER.warning(
            "[_get_mqtt_topic_from_entity] Entity '%s' not found in registry", entity_id
        )
        # Fallback: derive from entity_id
        device_name = entity_id.replace("lock.", "").replace("_", " ")
        mqtt_topic = f"zigbee2mqtt/{device_name}"
        _LOGGER.info(
            "[_get_mqtt_topic_from_entity] Using fallback topic from entity_id: %s",
            mqtt_topic,
        )
        return mqtt_topic
    
    _LOGGER.debug(
        "[_get_mqtt_topic_from_entity] Entity registry entry found: unique_id=%s, platform=%s, device_id=%s",
        entry.unique_id,
        entry.platform,
        entry.device_id,
    )
    
    # Try to get device info for better topic derivation
    if entry.device_id:
        from homeassistant.helpers import device_registry as dr
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(entry.device_id)
        
        if device:
            _LOGGER.debug(
                "[_get_mqtt_topic_from_entity] Device found: name=%s, name_by_user=%s, identifiers=%s",
                device.name,
                device.name_by_user,
                device.identifiers,
            )
            
            # For Z2M devices, the identifier often contains the friendly name
            # Format: {("mqtt", "zigbee2mqtt_0x00158d0001234567")} or similar
            for domain, identifier in device.identifiers:
                _LOGGER.debug(
                    "[_get_mqtt_topic_from_entity] Checking identifier: domain=%s, id=%s",
                    domain,
                    identifier,
                )
                if domain == "mqtt" and identifier.startswith("zigbee2mqtt_"):
                    # Extract the device name from the identifier
                    device_name = identifier.replace("zigbee2mqtt_", "")
                    mqtt_topic = f"zigbee2mqtt/{device_name}"
                    _LOGGER.info(
                        "[_get_mqtt_topic_from_entity] Derived topic from device identifier: %s",
                        mqtt_topic,
                    )
                    return mqtt_topic
            
            # If device has a name, use that
            if device.name:
                mqtt_topic = f"zigbee2mqtt/{device.name}"
                _LOGGER.info(
                    "[_get_mqtt_topic_from_entity] Derived topic from device name: %s",
                    mqtt_topic,
                )
                return mqtt_topic
    
    # Try to extract from unique_id
    if entry.unique_id:
        unique_id = entry.unique_id
        _LOGGER.debug(
            "[_get_mqtt_topic_from_entity] Trying to derive from unique_id: %s", unique_id
        )
        
        # Common Z2M format: "0x00158d0001234567_lock" or "friendly_name_lock"
        if "_" in unique_id:
            device_name = unique_id.rsplit("_", 1)[0]
        else:
            device_name = unique_id
            
        # If it looks like a Zigbee address, we can't derive a meaningful name
        if device_name.startswith("0x"):
            _LOGGER.warning(
                "[_get_mqtt_topic_from_entity] unique_id appears to be a Zigbee address. "
                "Using entity name as fallback."
            )
            device_name = entity_id.replace("lock.", "").replace("_", " ")
        
        mqtt_topic = f"zigbee2mqtt/{device_name}"
        _LOGGER.info(
            "[_get_mqtt_topic_from_entity] Derived topic from unique_id: %s", mqtt_topic
        )
        return mqtt_topic
    
    # Final fallback: derive from entity_id
    device_name = entity_id.replace("lock.", "").replace("_", " ")
    mqtt_topic = f"zigbee2mqtt/{device_name}"
    _LOGGER.warning(
        "[_get_mqtt_topic_from_entity] Using final fallback topic: %s", mqtt_topic
    )
    return mqtt_topic


def _get_lock_platform(hass: HomeAssistant, entity_id: str) -> str | None:
    """Return which integration (platform) owns the given lock entity.

    This is what lets us pick the right adapter automatically: entities
    created by ZHA report platform "zha", entities created by the MQTT
    integration (e.g. via Zigbee2MQTT) report platform "mqtt".
    """
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if not entry:
        _LOGGER.warning(
            "[_get_lock_platform] Entity '%s' not found in entity registry", entity_id
        )
        return None
    _LOGGER.debug(
        "[_get_lock_platform] Entity '%s' owned by platform '%s'", entity_id, entry.platform
    )
    return entry.platform


def _get_zha_ieee_from_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    """Resolve the IEEE address of a ZHA-managed lock entity.

    ZHA registers its devices in the device registry with an identifier
    tuple of the form ("zha", "<ieee address>"). We look that up via the
    entity's device_id rather than guessing from the entity_id/unique_id,
    since IEEE addresses aren't derivable from either of those.
    """
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)

    if not entry or not entry.device_id:
        _LOGGER.error(
            "[_get_zha_ieee_from_entity] Entity '%s' not found or has no device_id",
            entity_id,
        )
        return None

    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(entry.device_id)

    if not device:
        _LOGGER.error(
            "[_get_zha_ieee_from_entity] Device '%s' not found in device registry",
            entry.device_id,
        )
        return None

    for domain, identifier in device.identifiers:
        if domain == "zha":
            _LOGGER.info(
                "[_get_zha_ieee_from_entity] Resolved IEEE '%s' for entity '%s'",
                identifier,
                entity_id,
            )
            return identifier

    _LOGGER.error(
        "[_get_zha_ieee_from_entity] No 'zha' identifier found on device '%s' "
        "(identifiers=%s). Is this entity really managed by ZHA?",
        entry.device_id,
        device.identifiers,
    )
    return None


def _cancel_auto_lock(hass: HomeAssistant, entry_id: str) -> None:
    """Cancel any running auto-lock timer."""
    data = hass.data.get(DOMAIN, {})
    task = data.get("auto_lock_task")
    if task and not task.done():
        task.cancel()
        data["auto_lock_task"] = None


def _schedule_auto_lock(hass: HomeAssistant, entry: ConfigEntry, delay: int) -> None:
    """Start a delayed lock command, cancelling any previous timer."""
    _cancel_auto_lock(hass, entry.entry_id)
    lock_entity = hass.data[DOMAIN]["config"].get(CONF_LOCK_ENTITY)

    async def _do_lock() -> None:
        try:
            await asyncio.sleep(delay)
            _LOGGER.info("Auto-lock firing after %ds", delay)
            if lock_entity:
                await hass.services.async_call(
                    "lock", "lock", {"entity_id": lock_entity}, blocking=True
                )
        except asyncio.CancelledError:
            pass

    task = hass.async_create_task(_do_lock())
    hass.data[DOMAIN]["auto_lock_task"] = task


# Byte layout of the nimly_last_lock_unlock_source bitmap32 attribute (0x0100),
# confirmed against the upstream zhaquirks.nimly.lock converters:
# source = byte[3], action = byte[2], user_id = byte[1]<<8 | byte[0] (16-bit).
# Source/action values 0x00/0x02/0x03/0x04/0x0A and 0x01/0x02 respectively are
# upstream-confirmed; the failed_lock/failed_unlock/auto_lock entries below are
# our own reverse-engineered guesses since upstream leaves those undecoded.
_ACTIVITY_SOURCE_MAP = {
    0x00: "zigbee",
    0x01: "manual",
    0x02: "keypad",
    0x03: "fingerprint",
    0x04: "rfid",
    0x0A: "auto",
}
_ACTIVITY_ACTION_MAP = {
    0x01: "lock",
    0x02: "unlock",
    0x03: "failed_lock",    # invalid PIN/ID
    0x04: "failed_lock",    # invalid schedule
    0x05: "failed_unlock",  # invalid PIN/ID
    0x06: "failed_unlock",  # invalid schedule
    0x0A: "auto_lock",
}


def _get_doorlock_cluster(hass: HomeAssistant, zha_ieee: str, endpoint_id: int):
    """Thin wrapper kept for call-site compatibility."""
    return get_doorlock_cluster(hass, zha_ieee, endpoint_id)


# nimly_last_lock_unlock_source (0x0100) only ever reports *successful*
# lock/unlock actions — it never fires for a rejected PIN, so wrong-PIN
# detection can't live here. nimly_last_pin_code (0x0101) reports the raw
# digits typed on the keypad regardless of whether they were accepted, so
# that's what _process_pin_entry_event checks against known codes instead.
_ATTR_LOCK_ACTIVITY = 0x0100
_ATTR_LAST_PIN_CODE = 0x0101


def _process_activity_event(hass: HomeAssistant, attr_id: int, value) -> None:
    """Dispatch a DoorLock attribute report to the right handler."""
    if attr_id == _ATTR_LOCK_ACTIVITY:
        _process_lock_activity_event(hass, value)
    elif attr_id == _ATTR_LAST_PIN_CODE:
        _process_pin_entry_event(hass, value)


def _process_lock_activity_event(hass: HomeAssistant, value) -> None:
    """Decode a nimly_last_lock_unlock_source report and append it to the activity log."""
    from homeassistant.util.dt import utcnow

    try:
        val = int(value)
    except (TypeError, ValueError):
        try:
            val = int(value.value)
        except Exception:
            return
    try:
        b = val.to_bytes(4, "little")
    except (OverflowError, ValueError):
        return

    ts = utcnow().isoformat()

    # Confirmed layout — see _ACTIVITY_SOURCE_MAP/_ACTIVITY_ACTION_MAP comment.
    user_slot = b[0] | (b[1] << 8)
    action    = _ACTIVITY_ACTION_MAP.get(b[2], "unknown")
    source    = _ACTIVITY_SOURCE_MAP.get(b[3], "unknown")

    _LOGGER.debug(
        "NIMLY RAW EVENT 0x0100 = 0x%08x  bytes=[0x%02x,0x%02x,0x%02x,0x%02x]  "
        "user_id=%d action=%s source=%s",
        val, b[0], b[1], b[2], b[3],
        user_slot, action, source,
    )

    nimlykoder_data = hass.data.get(DOMAIN, {})

    # Persist the raw report + the decoded fields, independent of the
    # activity log, as a diagnostic trail.
    raw_ping = {
        "ts": ts,
        "raw_value": f"0x{val:08x}",
        "bytes": [f"0x{byte:02x}" for byte in b],
        "decoded": {"user_id": user_slot, "action": action, "source": source},
    }
    raw_ping_log = nimlykoder_data.get("raw_ping_log", [])
    raw_ping_log.insert(0, raw_ping)
    if len(raw_ping_log) > RAW_PING_LOG_MAX:
        raw_ping_log.pop()
    nimlykoder_data["raw_ping_log"] = raw_ping_log

    raw_ping_store = nimlykoder_data.get("raw_ping_store")
    if raw_ping_store:
        hass.async_create_task(raw_ping_store.async_save({"entries": raw_ping_log}))

    if action in ("failed_lock", "failed_unlock"):
        # No slot/user/name in the payload — don't expose which code was guessed.
        hass.bus.async_fire(EVENT_WRONG_PIN_ATTEMPT, {"ts": ts, "source": source})

    user_name = None
    storage = nimlykoder_data.get("storage")
    if storage and user_slot > 0:
        code_entry = storage.get(user_slot)
        if code_entry:
            user_name = code_entry.name

    activity = {
        "ts": ts,
        "action": action,
        "source": source,
        "slot": user_slot if user_slot > 0 else None,
        "name": user_name,
    }

    log = nimlykoder_data.get("activity_log", [])
    log.insert(0, activity)
    if len(log) > ACTIVITY_LOG_MAX:
        log.pop()
    nimlykoder_data["activity_log"] = log

    activity_store = nimlykoder_data.get("activity_store")
    if activity_store:
        hass.async_create_task(activity_store.async_save({"entries": log}))


def _process_pin_entry_event(hass: HomeAssistant, value) -> None:
    """Check a nimly_last_pin_code report against known codes.

    The bytes are BCD-packed (two decimal digits per byte), so `.hex()`
    reproduces the typed digits directly (e.g. b'\\x99\\x77' -> "9977").
    Fires EVENT_WRONG_PIN_ATTEMPT when the digits don't match any current,
    non-expired stored code.
    """
    from homeassistant.util.dt import utcnow

    try:
        entered_pin = bytes(value).hex()
    except (TypeError, ValueError):
        return
    if not entered_pin:
        return

    nimlykoder_data = hass.data.get(DOMAIN, {})
    storage = nimlykoder_data.get("storage")
    if storage is None:
        return

    if storage.find_by_pin(entered_pin) is not None:
        return  # Matches a known code — the 0x0100 report covers this as a normal unlock.

    ts = utcnow().isoformat()
    _LOGGER.debug("NIMLY wrong PIN entered on keypad (%d digits)", len(entered_pin))

    # No slot/user/pin in the payload — don't expose which code was guessed.
    hass.bus.async_fire(EVENT_WRONG_PIN_ATTEMPT, {"ts": ts, "source": "keypad"})

    activity = {
        "ts": ts,
        "action": "failed_unlock",
        "source": "keypad",
        "slot": None,
        "name": None,
    }
    log = nimlykoder_data.get("activity_log", [])
    log.insert(0, activity)
    if len(log) > ACTIVITY_LOG_MAX:
        log.pop()
    nimlykoder_data["activity_log"] = log

    activity_store = nimlykoder_data.get("activity_store")
    if activity_store:
        hass.async_create_task(activity_store.async_save({"entries": log}))


def _register_activity_listener(hass: HomeAssistant, zha_ieee: str, endpoint_id: int):
    """Attach to the DoorLock cluster using both listener APIs for maximum compatibility."""
    cluster = _get_doorlock_cluster(hass, zha_ieee, endpoint_id)
    if cluster is None:
        _LOGGER.warning(
            "Could not find DoorLock cluster for activity log (ieee=%s ep=%s)",
            zha_ieee, endpoint_id,
        )
        return None

    # --- Method 1: zigpy ListenableMixin — attribute_updated(attr_id, value) ---
    class _AttributeListener:
        def attribute_updated(self, attr_id, value, timestamp=None):
            _process_activity_event(hass, attr_id, value)

    listener_obj = _AttributeListener()
    cluster.add_listener(listener_obj)

    # --- Method 2: zigpy on_event — fired by some ZHA/zigpy versions ---
    def _on_event(event):
        _process_activity_event(hass, event.attribute_id, event.raw_value)

    unsub_event = None
    try:
        unsub_event = cluster.on_event("attribute_report", _on_event)
    except Exception:
        pass  # not all versions support this

    _LOGGER.info(
        "Activity listener registered for ieee=%s ep=%s (cluster=%s)",
        zha_ieee, endpoint_id, type(cluster).__name__,
    )

    def _unsub():
        try:
            cluster.remove_listener(listener_obj)
        except Exception:
            pass
        if unsub_event:
            try:
                unsub_event()
            except Exception:
                pass

    return _unsub


def _setup_door_sensor_listener(hass: HomeAssistant, door_sensor_entity: str):
    """Listen for door open/close events and append them to the activity log."""
    from homeassistant.util.dt import utcnow

    @callback
    def _on_door_state_changed(event) -> None:
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return
        # Skip unavailable / unknown / startup transitions from None
        if new_state.state not in ("on", "off"):
            return
        if old_state is None or old_state.state not in ("on", "off"):
            return
        action = "door_open" if new_state.state == "on" else "door_close"
        activity = {
            "ts": utcnow().isoformat(),
            "action": action,
            "source": "door",
            "slot": None,
            "name": new_state.attributes.get("friendly_name") or door_sensor_entity,
        }
        nimlykoder_data = hass.data.get(DOMAIN, {})
        log = nimlykoder_data.get("activity_log", [])
        log.insert(0, activity)
        if len(log) > ACTIVITY_LOG_MAX:
            log.pop()
        nimlykoder_data["activity_log"] = log
        activity_store = nimlykoder_data.get("activity_store")
        if activity_store:
            hass.async_create_task(activity_store.async_save({"entries": log}))

    return async_track_state_change_event(hass, [door_sensor_entity], _on_door_state_changed)


def _setup_auto_lock_listener(hass: HomeAssistant, entry: ConfigEntry, lock_entity: str):
    """Listen for lock state changes and manage the auto-lock timer."""

    @callback
    def _on_lock_state_changed(event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        state = new_state.state
        opts = entry.options
        if state == "unlocked":
            if opts.get(OPT_AUTO_LOCK_ENABLED, False):
                delay = int(opts.get(OPT_AUTO_LOCK_DELAY, 300))
                _LOGGER.debug("Lock unlocked — scheduling auto-lock in %ds", delay)
                _schedule_auto_lock(hass, entry, delay)
        elif state == "locked":
            _cancel_auto_lock(hass, entry.entry_id)

    return async_track_state_change_event(hass, [lock_entity], _on_lock_state_changed)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Nimlykoder from a config entry."""
    _LOGGER.info("[async_setup_entry] Starting Nimlykoder setup...")
    
    # Get configuration
    options = entry.options
    _LOGGER.debug("[async_setup_entry] Config options: %s", options)
    
    # Support both new (lock_entity) and legacy (mqtt_topic) config
    lock_entity = options.get(CONF_LOCK_ENTITY)
    mqtt_topic = options.get(CONF_MQTT_TOPIC)
    
    _LOGGER.info(
        "[async_setup_entry] Config - lock_entity=%s, legacy_mqtt_topic=%s",
        lock_entity,
        mqtt_topic,
    )
    
    lock_platform = None
    if lock_entity:
        lock_platform = _get_lock_platform(hass, lock_entity)

    zha_ieee = None
    zha_endpoint_id = options.get(CONF_ZHA_ENDPOINT_ID, DEFAULT_ZHA_ENDPOINT_ID)
    if isinstance(zha_endpoint_id, float):
        zha_endpoint_id = int(zha_endpoint_id)

    if lock_entity and lock_platform == "zha":
        # Lock is managed by ZHA - resolve its IEEE address, no MQTT needed
        _LOGGER.info("[async_setup_entry] Detected ZHA-managed lock entity '%s'", lock_entity)
        zha_ieee = _get_zha_ieee_from_entity(hass, lock_entity)
        if not zha_ieee:
            _LOGGER.error(
                "[async_setup_entry] Failed to resolve ZHA IEEE address for entity '%s'",
                lock_entity,
            )
            return False
        mqtt_topic = None
    elif lock_entity:
        # New config: derive MQTT topic from entity (Zigbee2MQTT/other MQTT locks)
        _LOGGER.info(
            "[async_setup_entry] Using entity selector config (platform=%s)", lock_platform
        )
        mqtt_topic = _get_mqtt_topic_from_entity(hass, lock_entity)
        if not mqtt_topic:
            _LOGGER.error(
                "[async_setup_entry] Failed to derive MQTT topic from entity '%s'",
                lock_entity,
            )
            return False
        _LOGGER.info(
            "[async_setup_entry] Derived MQTT topic '%s' from entity '%s'",
            mqtt_topic,
            lock_entity,
        )
    elif mqtt_topic:
        _LOGGER.info(
            "[async_setup_entry] Using legacy MQTT topic config: %s", mqtt_topic
        )
    else:
        # No config at all - shouldn't happen but handle gracefully
        _LOGGER.error("[async_setup_entry] No lock entity or MQTT topic configured!")
        return False
    
    # Ensure slot values are integers
    slot_min = options.get(CONF_SLOT_MIN, DEFAULT_SLOT_MIN)
    slot_max = options.get(CONF_SLOT_MAX, DEFAULT_SLOT_MAX)
    if isinstance(slot_min, float):
        slot_min = int(slot_min)
    if isinstance(slot_max, float):
        slot_max = int(slot_max)
    
    config = {
        CONF_LOCK_ENTITY: lock_entity,
        CONF_MQTT_TOPIC: mqtt_topic,
        CONF_ZHA_ENDPOINT_ID: zha_endpoint_id,
        CONF_SLOT_MIN: slot_min,
        CONF_SLOT_MAX: slot_max,
        CONF_RESERVED_SLOTS: options.get(CONF_RESERVED_SLOTS, DEFAULT_RESERVED_SLOTS),
        CONF_AUTO_EXPIRE: options.get(CONF_AUTO_EXPIRE, DEFAULT_AUTO_EXPIRE),
        CONF_CLEANUP_TIME: options.get(CONF_CLEANUP_TIME, DEFAULT_CLEANUP_TIME),
        CONF_OVERWRITE_PROTECTION: options.get(
            CONF_OVERWRITE_PROTECTION, DEFAULT_OVERWRITE_PROTECTION
        ),
    }
    
    _LOGGER.info(
        "[async_setup_entry] Final config - platform=%s, mqtt_topic=%s, zha_ieee=%s, "
        "zha_endpoint=%s, slots=%d-%d, auto_expire=%s",
        lock_platform,
        config[CONF_MQTT_TOPIC],
        zha_ieee,
        config[CONF_ZHA_ENDPOINT_ID],
        config[CONF_SLOT_MIN],
        config[CONF_SLOT_MAX],
        config[CONF_AUTO_EXPIRE],
    )

    # Initialize code storage
    _LOGGER.debug("[async_setup_entry] Initializing storage...")
    storage = NimlykoderStorage(hass)
    await storage.async_load()
    _LOGGER.info("[async_setup_entry] Storage loaded with %d entries", len(storage.list_entries()))

    # Load persistent activity log
    activity_store = Store(hass, ACTIVITY_STORAGE_VERSION, ACTIVITY_STORAGE_KEY)
    activity_data = await activity_store.async_load()
    activity_log = (activity_data or {}).get("entries", [])
    _LOGGER.info("[async_setup_entry] Activity log loaded with %d entries", len(activity_log))

    # Load persistent raw ping log (diagnostic — see _process_activity_event)
    raw_ping_store = Store(hass, RAW_PING_STORAGE_VERSION, RAW_PING_STORAGE_KEY)
    raw_ping_data = await raw_ping_store.async_load()
    raw_ping_log = (raw_ping_data or {}).get("entries", [])
    _LOGGER.info("[async_setup_entry] Raw ping log loaded with %d entries", len(raw_ping_log))

    # Initialize the code adapter - ZHA (direct ZCL commands) or MQTT/Zigbee2MQTT,
    # chosen automatically based on which integration owns the lock entity.
    _LOGGER.debug("[async_setup_entry] Initializing code adapter (platform=%s)...", lock_platform)
    if lock_platform == "zha":
        mqtt_adapter = ZhaDoorLockAdapter(
            hass, zha_ieee, config[CONF_ZHA_ENDPOINT_ID], entity_id=lock_entity
        )
    else:
        mqtt_adapter = MqttZ2mAdapter(hass, config[CONF_MQTT_TOPIC])

    # Verify the adapter's backing integration is available
    mqtt_available = await mqtt_adapter.verify_connection()
    if not mqtt_available:
        _LOGGER.warning(
            "[async_setup_entry] Adapter backend not available! "
            "PIN codes will NOT be sent to the lock. "
            "Please check that ZHA or MQTT is configured in Home Assistant."
        )
    else:
        _LOGGER.info("[async_setup_entry] Adapter connection verified successfully")

    # Store data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN] = {
        "storage": storage,
        "mqtt_adapter": mqtt_adapter,
        "config": config,
        "entry": entry,
        "cleanup_unsub": None,
        "auto_lock_task": None,
        "unsub_lock_listener": None,
        "unsub_door_listener": None,
        "activity_log": activity_log,
        "activity_store": activity_store,
        "raw_ping_log": raw_ping_log,
        "raw_ping_store": raw_ping_store,
        "unsub_activity_listener": None,
        "zha_ieee": zha_ieee,
    }

    # Forward to sensor / binary_sensor platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    _LOGGER.debug("[async_setup_entry] Registering services...")
    await async_setup_services(hass)

    # Register WebSocket handlers
    async_register_websocket_handlers(hass)

    # Register panel
    await async_register_panel(hass)

    # Set up auto-lock listener if a lock entity is configured
    if lock_entity:
        unsub = _setup_auto_lock_listener(hass, entry, lock_entity)
        hass.data[DOMAIN]["unsub_lock_listener"] = unsub

    # Set up door sensor listener if configured
    door_sensor = entry.options.get(CONF_DOOR_SENSOR)
    if door_sensor:
        unsub_door = _setup_door_sensor_listener(hass, door_sensor)
        hass.data[DOMAIN]["unsub_door_listener"] = unsub_door

    # Set up ZHA activity log listener (ZHA locks only).
    # ZHA device proxies may not be populated yet even after after_dependencies
    # resolves, so we try immediately and fall back to a background retry loop.
    if lock_platform == "zha" and zha_ieee:
        try:
            unsub_act = _register_activity_listener(hass, zha_ieee, zha_endpoint_id)
        except Exception as exc:
            _LOGGER.warning("Error registering activity listener: %s", exc)
            unsub_act = None
        hass.data[DOMAIN]["unsub_activity_listener"] = unsub_act
        if unsub_act is None:
            async def _retry_activity_listener():
                for delay in (5, 10, 20, 30, 60):
                    await asyncio.sleep(delay)
                    data = hass.data.get(DOMAIN)
                    if not data:
                        return  # integration unloaded
                    if data.get("unsub_activity_listener"):
                        return  # already registered
                    unsub = _register_activity_listener(hass, zha_ieee, zha_endpoint_id)
                    if unsub is not None:
                        data["unsub_activity_listener"] = unsub
                        _LOGGER.info("Activity listener registered after deferred retry")
                        return
                _LOGGER.warning(
                    "Could not register activity listener after all retries — "
                    "ZHA cluster not found for ieee=%s ep=%s", zha_ieee, zha_endpoint_id
                )
            hass.async_create_task(_retry_activity_listener())

    # Set up scheduler for expired code cleanup
    if config[CONF_AUTO_EXPIRE]:
        unsub = await async_setup_cleanup_scheduler(hass, config[CONF_CLEANUP_TIME])
        hass.data[DOMAIN]["cleanup_unsub"] = unsub

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.info("Nimlykoder integration set up successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data.get(DOMAIN)
    if data:
        # Cancel auto-lock timer
        task = data.get("auto_lock_task")
        if task and not task.done():
            task.cancel()

        # Unsubscribe lock state listener
        unsub = data.get("unsub_lock_listener")
        if unsub:
            unsub()

        # Unsubscribe door sensor listener
        unsub_door = data.get("unsub_door_listener")
        if unsub_door:
            unsub_door()

        # Unsubscribe activity listener
        unsub_act = data.get("unsub_activity_listener")
        if unsub_act:
            unsub_act()

        # Cancel cleanup scheduler
        if data.get("cleanup_unsub"):
            data["cleanup_unsub"]()

    # Unload sensor / binary_sensor platforms
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Unregister services
    await async_unload_services(hass)

    # Unregister panel
    await async_unregister_panel(hass)

    # Clean up data
    hass.data.pop(DOMAIN, None)

    _LOGGER.info("Nimlykoder integration unloaded")
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_cleanup_scheduler(hass: HomeAssistant, cleanup_time: str):
    """Set up daily cleanup scheduler. Returns unsub function."""
    try:
        # Parse cleanup time (format: HH:MM:SS)
        time_parts = cleanup_time.split(":")
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        second = int(time_parts[2]) if len(time_parts) > 2 else 0

        @callback
        def cleanup_expired_codes(now):
            """Clean up expired guest codes."""
            hass.async_create_task(_async_cleanup_expired_codes(hass))

        # Schedule daily cleanup
        unsub = async_track_time_change(
            hass, cleanup_expired_codes, hour=hour, minute=minute, second=second
        )

        _LOGGER.info(
            "Scheduled daily expired code cleanup at %02d:%02d:%02d",
            hour, minute, second
        )
        return unsub

    except Exception as err:
        _LOGGER.error("Failed to set up cleanup scheduler: %s", err)
        return None


async def _async_cleanup_expired_codes(hass: HomeAssistant) -> None:
    """Clean up expired guest codes."""
    try:
        data = hass.data.get(DOMAIN)
        if not data:
            _LOGGER.warning("Nimlykoder data not available for cleanup")
            return

        config = data["config"]
        if not config.get(CONF_AUTO_EXPIRE, True):
            _LOGGER.debug("Auto-expire is disabled, skipping cleanup")
            return

        storage = data["storage"]
        mqtt_adapter = data["mqtt_adapter"]

        today = date.today()
        expired_slots = storage.expired_guest_slots(today)

        if not expired_slots:
            _LOGGER.debug("No expired guest codes to clean up")
            return

        _LOGGER.info("Starting cleanup of %d expired guest codes", len(expired_slots))
        removed_count = 0

        for slot in expired_slots:
            try:
                entry = storage.get(slot)
                name = entry.name if entry else f"Slot {slot}"
                
                # Remove from the lock
                await mqtt_adapter.remove_code(slot)
                # Remove from storage
                await storage.remove(slot)
                
                _LOGGER.info(
                    "Removed expired code '%s' from slot %s", name, slot
                )
                removed_count += 1
            except Exception as err:
                _LOGGER.error(
                    "Failed to remove expired code from slot %s: %s", slot, err
                )

        _LOGGER.info(
            "Cleanup completed: removed %d of %d expired codes",
            removed_count, len(expired_slots)
        )

    except Exception as err:
        _LOGGER.error("Error during cleanup: %s", err)
