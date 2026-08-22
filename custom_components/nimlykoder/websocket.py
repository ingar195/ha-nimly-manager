"""WebSocket API for Nimlykoder integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    WS_TYPE_LIST,
    WS_TYPE_ADD,
    WS_TYPE_REMOVE,
    WS_TYPE_UPDATE_EXPIRY,
    WS_TYPE_UPDATE_NAME,
    WS_TYPE_UPDATE_PIN,
    WS_TYPE_SUGGEST_SLOTS,
    WS_TYPE_CONFIG,
    WS_TYPE_TRANSLATIONS,
    WS_TYPE_SET_AUTO_LOCK,
    WS_TYPE_ACTIVITY,
    WS_TYPE_GET_LOCK_SETTINGS,
    WS_TYPE_SET_LOCK_SETTING,
    TYPE_PERMANENT,
    TYPE_GUEST,
    CONF_AUTO_EXPIRE,
    CONF_CLEANUP_TIME,
    CONF_LOCK_ENTITY,
    CONF_ZHA_ENDPOINT_ID,
    DEFAULT_ZHA_ENDPOINT_ID,
    OPT_AUTO_LOCK_ENABLED,
    OPT_AUTO_LOCK_DELAY,
)
from .zha_helpers import get_doorlock_cluster, LOCK_SETTINGS

_LOGGER = logging.getLogger(__name__)
PANEL_TRANSLATION_KEYS = frozenset({"title", "subtitle", "add_code"})


@callback
def async_register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register WebSocket handlers."""
    websocket_api.async_register_command(hass, handle_list)
    websocket_api.async_register_command(hass, handle_add)
    websocket_api.async_register_command(hass, handle_remove)
    websocket_api.async_register_command(hass, handle_update_expiry)
    websocket_api.async_register_command(hass, handle_update_name)
    websocket_api.async_register_command(hass, handle_update_pin)
    websocket_api.async_register_command(hass, handle_suggest_slots)
    websocket_api.async_register_command(hass, handle_config)
    websocket_api.async_register_command(hass, handle_translations)
    websocket_api.async_register_command(hass, handle_set_auto_lock)
    websocket_api.async_register_command(hass, handle_activity)
    websocket_api.async_register_command(hass, handle_get_lock_settings)
    websocket_api.async_register_command(hass, handle_set_lock_setting)


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_LIST,
    }
)
@websocket_api.async_response
async def handle_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle list command."""
    try:
        data = hass.data[DOMAIN]
        storage = data["storage"]

        entries = storage.list_entries()
        connection.send_result(
            msg["id"],
            {"codes": [entry.to_dict() for entry in entries]},
        )
    except Exception as err:
        _LOGGER.error("Error listing codes: %s", err)
        connection.send_error(msg["id"], "list_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ADD,
        vol.Required("name"): str,
        vol.Required("pin_code"): str,
        vol.Required("code_type"): vol.In([TYPE_PERMANENT, TYPE_GUEST]),
        vol.Optional("expiry"): str,
        vol.Optional("slot"): int,
        vol.Optional("force", default=False): bool,
    }
)
@websocket_api.async_response
async def handle_add(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle add command."""
    try:
        data = hass.data[DOMAIN]
        storage = data["storage"]
        mqtt_adapter = data["mqtt_adapter"]
        config = data["config"]

        name = msg["name"]
        pin_code = msg["pin_code"]
        code_type = msg["code_type"]
        expiry = msg.get("expiry")
        preferred_slot = msg.get("slot")
        force = msg.get("force", False)

        # Validate PIN code is 4-6 digits
        if not pin_code.isdigit() or not 4 <= len(pin_code) <= 6:
            connection.send_error(
                msg["id"], "invalid_input", "PIN code must be 4-6 digits"
            )
            return

        # Policy enforcement
        if code_type == TYPE_GUEST and not expiry:
            connection.send_error(
                msg["id"], "invalid_input", "Guest codes must have an expiry date"
            )
            return

        # Validate expiry format if provided
        if expiry:
            try:
                datetime.fromisoformat(expiry)
            except ValueError as err:
                connection.send_error(
                    msg["id"], "invalid_input", f"Invalid expiry date format: {err}"
                )
                return

        # Determine slot
        if preferred_slot is not None:
            slot = preferred_slot
            # Slot 0 means "no specific user" in decoded lock activity —
            # never allow a real code to occupy it, regardless of slot_min.
            if slot == 0:
                connection.send_error(
                    msg["id"], "invalid_slot", "Slot 0 is reserved and cannot be used"
                )
                return
            # Check bounds
            if slot < config["slot_min"] or slot > config["slot_max"]:
                connection.send_error(
                    msg["id"],
                    "invalid_slot",
                    f"Slot {slot} outside configured range",
                )
                return
            # Check if occupied
            if storage.is_slot_occupied(slot):
                if not force and config.get("overwrite_protection", True):
                    connection.send_error(
                        msg["id"],
                        "slot_occupied",
                        f"Slot {slot} is occupied. Use force to overwrite",
                    )
                    return
        else:
            # Auto-select slot
            slot = storage.find_first_free_slot(
                config["slot_min"],
                config["slot_max"],
                config["reserved_slots"],
            )
            if slot is None:
                connection.send_error(
                    msg["id"], "no_free_slots", "No free slots available"
                )
                return

        # Check reserved slots for auto-assignment
        if preferred_slot is None and slot in config["reserved_slots"]:
            connection.send_error(
                msg["id"], "slot_reserved", f"Slot {slot} is reserved"
            )
            return

        # Send to the lock first (via ZHA or MQTT, depending on configured adapter)
        try:
            await mqtt_adapter.add_code(slot, pin_code)
        except Exception as err:
            connection.send_error(
                msg["id"], "adapter_error", f"Failed to add code to lock: {err}"
            )
            return

        # Then store
        try:
            entry = await storage.add(slot, name, code_type, expiry, pin=pin_code)
            _LOGGER.info("Added %s code '%s' to slot %s", code_type, name, slot)
            connection.send_result(msg["id"], {"entry": entry.to_dict()})
        except Exception as err:
            # Try to clean up lock if storage fails
            try:
                await mqtt_adapter.remove_code(slot)
            except Exception:
                pass
            connection.send_error(msg["id"], "storage_error", str(err))
            return

    except Exception as err:
        _LOGGER.error("Error adding code: %s", err)
        connection.send_error(msg["id"], "add_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_REMOVE,
        vol.Required("slot"): int,
    }
)
@websocket_api.async_response
async def handle_remove(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle remove command."""
    try:
        data = hass.data[DOMAIN]
        storage = data["storage"]
        mqtt_adapter = data["mqtt_adapter"]

        slot = msg["slot"]

        # Check if slot exists
        entry = storage.get(slot)
        if entry is None:
            connection.send_error(msg["id"], "not_found", f"Slot {slot} not found")
            return

        # Remove from the lock
        try:
            await mqtt_adapter.remove_code(slot)
        except Exception as err:
            connection.send_error(
                msg["id"], "adapter_error", f"Failed to remove code from lock: {err}"
            )
            return

        # Remove from storage
        await storage.remove(slot)
        _LOGGER.info("Removed code from slot %s", slot)
        connection.send_result(msg["id"], {"success": True})

    except Exception as err:
        _LOGGER.error("Error removing code: %s", err)
        connection.send_error(msg["id"], "remove_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_UPDATE_EXPIRY,
        vol.Required("slot"): int,
        vol.Optional("expiry"): str,
    }
)
@websocket_api.async_response
async def handle_update_expiry(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle update_expiry command."""
    try:
        data = hass.data[DOMAIN]
        storage = data["storage"]

        slot = msg["slot"]
        expiry = msg.get("expiry")

        # Validate expiry format if provided
        if expiry:
            try:
                datetime.fromisoformat(expiry)
            except ValueError as err:
                connection.send_error(
                    msg["id"], "invalid_input", f"Invalid expiry date format: {err}"
                )
                return

        # Update storage
        try:
            entry = await storage.update_expiry(slot, expiry)
            _LOGGER.info("Updated expiry for slot %s to %s", slot, expiry)
            connection.send_result(msg["id"], {"entry": entry.to_dict()})
        except Exception as err:
            connection.send_error(msg["id"], "update_failed", str(err))

    except Exception as err:
        _LOGGER.error("Error updating expiry: %s", err)
        connection.send_error(msg["id"], "update_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_UPDATE_NAME,
        vol.Required("slot"): int,
        vol.Required("name"): str,
    }
)
@websocket_api.async_response
async def handle_update_name(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle update_name command."""
    try:
        data = hass.data[DOMAIN]
        storage = data["storage"]

        slot = msg["slot"]
        name = msg["name"]

        if not name or not name.strip():
            connection.send_error(msg["id"], "invalid_input", "Name cannot be empty")
            return

        # Check if slot exists
        entry = storage.get(slot)
        if entry is None:
            connection.send_error(msg["id"], "not_found", f"Slot {slot} not found")
            return

        # Update storage
        try:
            entry = await storage.update_name(slot, name)
            _LOGGER.info("Updated name for slot %s to '%s'", slot, name)
            connection.send_result(msg["id"], {"entry": entry.to_dict()})
        except Exception as err:
            connection.send_error(msg["id"], "update_failed", str(err))
            return

    except Exception as err:
        _LOGGER.error("Error updating name: %s", err)
        connection.send_error(msg["id"], "update_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_UPDATE_PIN,
        vol.Required("slot"): int,
        vol.Required("pin_code"): str,
    }
)
@websocket_api.async_response
async def handle_update_pin(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle update_pin command - update PIN code for existing slot."""
    try:
        data = hass.data[DOMAIN]
        storage = data["storage"]
        mqtt_adapter = data["mqtt_adapter"]

        slot = msg["slot"]
        pin_code = msg["pin_code"]

        # Check if slot exists
        entry = storage.get(slot)
        if entry is None:
            connection.send_error(msg["id"], "not_found", f"Slot {slot} not found")
            return

        # Validate PIN code is 4-6 digits
        if not pin_code.isdigit() or not 4 <= len(pin_code) <= 6:
            connection.send_error(
                msg["id"], "invalid_input", "PIN code must be 4-6 digits"
            )
            return

        # Send new PIN to the lock (via ZHA or MQTT, depending on configured adapter)
        _LOGGER.info("Updating PIN for slot %s", slot)
        try:
            await mqtt_adapter.add_code(slot, pin_code)
        except Exception as err:
            connection.send_error(
                msg["id"], "adapter_error", f"Failed to update PIN on lock: {err}"
            )
            return

        # Persist the new PIN in storage
        try:
            entry = await storage.update_pin(slot, pin_code)
        except Exception as err:
            _LOGGER.warning("Failed to persist PIN in storage: %s", err)

        _LOGGER.info("Successfully updated PIN for slot %s", slot)
        connection.send_result(msg["id"], {"success": True, "entry": entry.to_dict()})

    except Exception as err:
        _LOGGER.error("Error updating PIN: %s", err)
        connection.send_error(msg["id"], "update_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_SUGGEST_SLOTS,
        vol.Optional("count", default=5): int,
    }
)
@websocket_api.async_response
async def handle_suggest_slots(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle suggest_slots command."""
    try:
        data = hass.data[DOMAIN]
        storage = data["storage"]
        config = data["config"]

        count = msg.get("count", 5)
        suggestions = []

        for slot in range(max(config["slot_min"], 1), config["slot_max"] + 1):
            if len(suggestions) >= count:
                break
            if slot in config["reserved_slots"]:
                continue
            if not storage.is_slot_occupied(slot):
                suggestions.append(slot)

        connection.send_result(msg["id"], {"slots": suggestions})

    except Exception as err:
        _LOGGER.error("Error suggesting slots: %s", err)
        connection.send_error(msg["id"], "suggest_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_CONFIG,
    }
)
@websocket_api.async_response
async def handle_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle config command - returns current configuration."""
    try:
        data = hass.data[DOMAIN]
        config = data["config"]

        # Read auto-lock state from nimlykoder's own config entry
        entry = data["entry"]
        auto_lock_enabled = bool(entry.options.get(OPT_AUTO_LOCK_ENABLED, False))
        auto_lock_delay = int(entry.options.get(OPT_AUTO_LOCK_DELAY, 300))

        # Auto-discover the ZHA battery sensor on the same device as the lock.
        # Returns the entity_id so the panel can watch hass.states directly.
        # Find battery sensor: prefer the nimlykoder-owned one, fall back to ZHA.
        battery_entity = None
        lock_entity_id = config.get(CONF_LOCK_ENTITY, "")
        try:
            ent_reg = er.async_get(hass)
            # 1. Look for nimlykoder battery entity (always reliable)
            nimly_battery = f"{entry.entry_id}_battery"
            for ent in ent_reg.entities.values():
                if ent.unique_id == nimly_battery and not ent.disabled_by:
                    battery_entity = ent.entity_id
                    break
            # 2. Fallback: ZHA battery sensor on the same device
            if battery_entity is None and lock_entity_id:
                lock_entry = ent_reg.async_get(lock_entity_id)
                if lock_entry and lock_entry.device_id:
                    for ent in er.async_entries_for_device(ent_reg, lock_entry.device_id):
                        if ent.domain != "sensor" or ent.disabled_by:
                            continue
                        dc = str(ent.device_class or ent.original_device_class or "")
                        if dc == "battery":
                            battery_entity = ent.entity_id
                            break
                        state = hass.states.get(ent.entity_id)
                        if state and state.attributes.get("device_class") == "battery":
                            battery_entity = ent.entity_id
                            break
        except Exception:
            pass

        connection.send_result(
            msg["id"],
            {
                "auto_expire": config.get(CONF_AUTO_EXPIRE, True),
                "cleanup_time": config.get(CONF_CLEANUP_TIME, "03:00:00"),
                "lock_entity": lock_entity_id,
                "door_sensor": entry.options.get("door_sensor") or None,
                "battery_entity": battery_entity,
                "auto_lock_enabled": auto_lock_enabled,
                "auto_lock_delay": auto_lock_delay,
            },
        )

    except Exception as err:
        _LOGGER.error("Error getting config: %s", err)
        connection.send_error(msg["id"], "config_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_TRANSLATIONS,
    }
)
@websocket_api.async_response
async def handle_translations(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle translations command - returns panel translations for current language."""
    import json
    from pathlib import Path

    try:
        # Get user's language from hass config
        language = hass.config.language or "en"

        # Path to panel translation overrides
        translations_dir = Path(__file__).parent / "panel_translations"

        # Try to load the user's language, fallback to English
        translation_file = translations_dir / f"{language}.json"

        def _load_translations() -> dict:
            """Load translations from file (runs in executor to avoid blocking)."""
            file_to_load = translation_file
            if not file_to_load.exists():
                file_to_load = translations_dir / "en.json"
            with open(file_to_load, "r", encoding="utf-8") as f:
                return json.load(f)

        # Run file I/O in executor to avoid blocking the event loop
        translations = await hass.async_add_executor_job(_load_translations)

        # Keep support for both direct panel dictionaries and legacy nested format
        if isinstance(translations, dict) and PANEL_TRANSLATION_KEYS.issubset(
            translations
        ):
            panel_translations = translations
        elif isinstance(translations.get("panel"), dict):
            panel_translations = translations["panel"]
        else:
            panel_translations = {}

        connection.send_result(
            msg["id"],
            {
                "language": language,
                "translations": panel_translations,
            },
        )

    except Exception as err:
        _LOGGER.error("Error getting translations: %s", err)
        connection.send_error(msg["id"], "translations_failed", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_SET_AUTO_LOCK,
        vol.Required("enabled"): bool,
        vol.Optional("delay", default=300): int,
    }
)
@websocket_api.async_response
async def handle_set_auto_lock(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Enable or disable persistent auto-lock, stored in nimlykoder's config entry.

    The auto-lock listener in __init__.py reads entry.options live, so the
    change takes effect immediately without a restart.
    """
    try:
        enabled = msg["enabled"]
        delay = max(5, int(msg.get("delay", 300)))

        data = hass.data.get(DOMAIN)
        if not data:
            connection.send_error(msg["id"], "set_auto_lock_failed", "Nimlykoder not loaded")
            return

        entry = data["entry"]
        new_options = {
            **entry.options,
            OPT_AUTO_LOCK_ENABLED: enabled,
            OPT_AUTO_LOCK_DELAY: delay,
        }
        hass.config_entries.async_update_entry(entry, options=new_options)

        _LOGGER.info(
            "Auto-lock %s (delay=%ds) saved to nimlykoder config entry",
            "enabled" if enabled else "disabled",
            delay,
        )

        connection.send_result(
            msg["id"],
            {"success": True, "enabled": enabled, "delay": delay},
        )

    except Exception as err:
        _LOGGER.error("Error setting auto-lock: %s", err)
        connection.send_error(msg["id"], "set_auto_lock_failed", str(err))


@websocket_api.websocket_command({vol.Required("type"): WS_TYPE_ACTIVITY})
@websocket_api.async_response
async def handle_activity(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the in-memory activity log for the nimlykoder lock."""
    try:
        data = hass.data.get(DOMAIN, {})
        log = data.get("activity_log", [])
        connection.send_result(msg["id"], {"entries": log})
    except Exception as err:
        _LOGGER.error("Error getting activity log: %s", err)
        connection.send_error(msg["id"], "activity_failed", str(err))


@websocket_api.websocket_command({vol.Required("type"): WS_TYPE_GET_LOCK_SETTINGS})
@websocket_api.async_response
async def handle_get_lock_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Read current DoorLock settings directly from the Zigbee device."""
    data = hass.data.get(DOMAIN, {})
    zha_ieee = data.get("zha_ieee")
    endpoint_id = data.get("config", {}).get(CONF_ZHA_ENDPOINT_ID, DEFAULT_ZHA_ENDPOINT_ID)

    if not zha_ieee:
        connection.send_error(msg["id"], "not_zha", "Lock is not a ZHA device")
        return

    cluster = get_doorlock_cluster(hass, zha_ieee, endpoint_id)
    if cluster is None:
        connection.send_error(
            msg["id"], "cluster_unavailable",
            "DoorLock cluster not reachable — interact with the lock first to wake it"
        )
        return

    attr_ids = [meta["attr_id"] for meta in LOCK_SETTINGS.values()]
    try:
        result, _failed = await cluster.read_attributes(attr_ids, allow_cache=False)
    except Exception as err:
        connection.send_error(msg["id"], "read_failed", str(err))
        return

    # Build response keyed by setting name; value may be an enum — coerce to int/bool
    settings = {}
    for name, meta in LOCK_SETTINGS.items():
        raw = result.get(meta["attr_id"])
        if raw is None:
            # Try by attribute name in case zigpy keyed by name
            raw = result.get(name)
        if raw is None:
            continue
        try:
            settings[name] = bool(raw) if meta["type"] == "bool" else int(raw)
        except Exception:
            settings[name] = raw

    connection.send_result(msg["id"], {"settings": settings, "schema": LOCK_SETTINGS})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_SET_LOCK_SETTING,
        vol.Required("setting"): str,
        vol.Required("value"): vol.Any(bool, int),
    }
)
@websocket_api.async_response
async def handle_set_lock_setting(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Write a single DoorLock attribute to the Zigbee device."""
    setting = msg["setting"]
    if setting not in LOCK_SETTINGS:
        connection.send_error(msg["id"], "invalid_setting", f"Unknown setting: {setting}")
        return

    data = hass.data.get(DOMAIN, {})
    zha_ieee = data.get("zha_ieee")
    endpoint_id = data.get("config", {}).get(CONF_ZHA_ENDPOINT_ID, DEFAULT_ZHA_ENDPOINT_ID)

    if not zha_ieee:
        connection.send_error(msg["id"], "not_zha", "Lock is not a ZHA device")
        return

    cluster = get_doorlock_cluster(hass, zha_ieee, endpoint_id)
    if cluster is None:
        connection.send_error(
            msg["id"], "cluster_unavailable",
            "DoorLock cluster not reachable — interact with the lock first to wake it"
        )
        return

    meta = LOCK_SETTINGS[setting]
    value = msg["value"]
    if meta["type"] == "bool":
        value = bool(value)
    elif meta["type"] in ("int", "select"):
        value = int(value)

    try:
        result = await cluster.write_attributes({setting: value})
        _LOGGER.info("Lock setting %s set to %s (result=%s)", setting, value, result)
        connection.send_result(msg["id"], {"success": True, "setting": setting, "value": value})
    except Exception as err:
        _LOGGER.error("Error writing lock setting %s=%s: %s", setting, value, err)
        connection.send_error(msg["id"], "write_failed", str(err))
