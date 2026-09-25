"""WebSocket API for Nimlykoder integration.

User commands (list/add/remove/update_*) act on the one shared user list and
take an optional `locks` list. Lock commands (config, activity, auto-lock,
lock settings) take an optional `entry_id`; omitted means the original lock.
"""
from __future__ import annotations

import functools
import json
import logging
from pathlib import Path
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
    WS_TYPE_UPDATE_START,
    WS_TYPE_UPDATE_NAME,
    WS_TYPE_UPDATE_PIN,
    WS_TYPE_UPDATE_LOCKS,
    WS_TYPE_SUGGEST_SLOTS,
    WS_TYPE_CONFIG,
    WS_TYPE_ENTRIES,
    WS_TYPE_RESYNC,
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
from .helpers import (
    get_entry_data,
    get_users,
    loaded_entries,
    lock_title,
    resolve_locks,
)
from .users import (
    async_add_user,
    async_remove_user,
    async_resync,
    async_update_expiry,
    async_update_locks,
    async_update_pin,
    async_update_start,
    suggest_slots,
)
from .zha_helpers import get_doorlock_cluster, LOCK_SETTINGS

_LOGGER = logging.getLogger(__name__)
PANEL_TRANSLATION_KEYS = frozenset({"title", "subtitle", "add_code"})

LOCKS_FIELD = [str]


def _guarded(error_code: str):
    """Turn a `(hass, msg) -> result` coroutine into a websocket handler.

    A raised HomeAssistantError becomes a websocket error with its message
    (what the panel shows); anything else is logged and reported the same way.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
            try:
                result = await func(hass, msg)
            except HomeAssistantError as err:
                connection.send_error(msg["id"], error_code, str(err))
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Error in %s", msg.get("type"))
                connection.send_error(msg["id"], error_code, str(err))
            else:
                connection.send_result(msg["id"], result)

        return wrapper

    return decorator


@callback
def async_register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register WebSocket handlers."""
    for handler in (
        handle_list,
        handle_add,
        handle_remove,
        handle_update_expiry,
        handle_update_start,
        handle_update_name,
        handle_update_pin,
        handle_update_locks,
        handle_suggest_slots,
        handle_config,
        handle_entries,
        handle_resync,
        handle_translations,
        handle_set_auto_lock,
        handle_activity,
        handle_get_lock_settings,
        handle_set_lock_setting,
    ):
        websocket_api.async_register_command(hass, handler)


# --------------------------------------------------------------------------
# Shared user list
# --------------------------------------------------------------------------


@websocket_api.websocket_command({vol.Required("type"): WS_TYPE_LIST})
@websocket_api.async_response
@_guarded("list_failed")
async def handle_list(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    return {"codes": [e.to_dict() for e in get_users(hass).list_entries()]}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ADD,
        vol.Required("name"): str,
        vol.Required("pin_code"): str,
        vol.Required("code_type"): vol.In([TYPE_PERMANENT, TYPE_GUEST]),
        vol.Optional("expiry"): str,
        vol.Optional("start"): str,
        vol.Optional("slot"): int,
        vol.Optional("force", default=False): bool,
        vol.Optional("locks"): LOCKS_FIELD,
    }
)
@websocket_api.async_response
@_guarded("add_failed")
async def handle_add(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    entry = await async_add_user(
        hass,
        name=msg["name"],
        pin_code=msg["pin_code"],
        code_type=msg["code_type"],
        expiry=msg.get("expiry"),
        start=msg.get("start"),
        slot=msg.get("slot"),
        force=msg.get("force", False),
        locks=msg.get("locks"),
    )
    return {"entry": entry.to_dict()}


@websocket_api.websocket_command(
    {vol.Required("type"): WS_TYPE_REMOVE, vol.Required("slot"): int}
)
@websocket_api.async_response
@_guarded("remove_failed")
async def handle_remove(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    await async_remove_user(hass, msg["slot"])
    return {"success": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_UPDATE_EXPIRY,
        vol.Required("slot"): int,
        vol.Optional("expiry"): vol.Any(str, None),
    }
)
@websocket_api.async_response
@_guarded("update_failed")
async def handle_update_expiry(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    entry = await async_update_expiry(hass, msg["slot"], msg.get("expiry"))
    return {"entry": entry.to_dict()}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_UPDATE_START,
        vol.Required("slot"): int,
        vol.Optional("start"): vol.Any(str, None),
    }
)
@websocket_api.async_response
@_guarded("update_failed")
async def handle_update_start(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    entry = await async_update_start(hass, msg["slot"], msg.get("start"))
    return {"entry": entry.to_dict()}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_UPDATE_NAME,
        vol.Required("slot"): int,
        vol.Required("name"): str,
    }
)
@websocket_api.async_response
@_guarded("update_failed")
async def handle_update_name(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    storage = get_users(hass)
    slot = msg["slot"]
    if storage.get(slot) is None:
        raise HomeAssistantError(f"Slot {slot} not found")
    entry = await storage.update_name(slot, msg["name"])
    return {"entry": entry.to_dict()}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_UPDATE_PIN,
        vol.Required("slot"): int,
        vol.Required("pin_code"): str,
    }
)
@websocket_api.async_response
@_guarded("update_failed")
async def handle_update_pin(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    entry = await async_update_pin(hass, msg["slot"], msg["pin_code"])
    return {"success": True, "entry": entry.to_dict()}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_UPDATE_LOCKS,
        vol.Required("slot"): int,
        vol.Required("locks"): LOCKS_FIELD,
    }
)
@websocket_api.async_response
@_guarded("update_failed")
async def handle_update_locks(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    entry = await async_update_locks(hass, msg["slot"], msg["locks"])
    return {"entry": entry.to_dict()}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_SUGGEST_SLOTS,
        vol.Optional("count", default=5): int,
        vol.Optional("locks"): LOCKS_FIELD,
        vol.Optional("code_type", default=TYPE_PERMANENT): vol.In(
            [TYPE_PERMANENT, TYPE_GUEST]
        ),
    }
)
@websocket_api.async_response
@_guarded("suggest_failed")
async def handle_suggest_slots(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    lock_ids = resolve_locks(hass, msg.get("locks"))
    return {"slots": suggest_slots(hass, lock_ids, msg["code_type"], msg["count"])}


@websocket_api.websocket_command(
    {vol.Required("type"): WS_TYPE_RESYNC, vol.Optional("locks"): LOCKS_FIELD}
)
@websocket_api.async_response
@_guarded("resync_failed")
async def handle_resync(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    summary = await async_resync(hass, msg.get("locks"))
    return {
        "locks": [
            {"entry_id": lock_id, "title": lock_title(hass, lock_id), **result}
            for lock_id, result in summary.items()
        ]
    }


# --------------------------------------------------------------------------
# Locks
# --------------------------------------------------------------------------


@websocket_api.websocket_command({vol.Required("type"): WS_TYPE_ENTRIES})
@websocket_api.async_response
@_guarded("entries_failed")
async def handle_entries(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    """The loaded locks, original first."""
    loaded = loaded_entries(hass)
    locks = []
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        data = loaded.get(config_entry.entry_id)
        if data is None:
            continue
        locks.append(
            {
                "entry_id": config_entry.entry_id,
                "title": config_entry.title,
                "lock_entity": data["config"].get(CONF_LOCK_ENTITY),
            }
        )
    return {"locks": locks}


@websocket_api.websocket_command(
    {vol.Required("type"): WS_TYPE_CONFIG, vol.Optional("entry_id"): str}
)
@websocket_api.async_response
@_guarded("config_failed")
async def handle_config(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    """Configuration of one lock."""
    data = get_entry_data(hass, msg.get("entry_id"))
    config = data["config"]
    entry = data["entry"]
    auto_lock_enabled = bool(entry.options.get(OPT_AUTO_LOCK_ENABLED, False))
    auto_lock_delay = int(entry.options.get(OPT_AUTO_LOCK_DELAY, 300))

    # Find battery sensor: prefer the nimlykoder-owned one, fall back to ZHA,
    # so the panel can watch hass.states directly.
    battery_entity = None
    lock_entity_id = config.get(CONF_LOCK_ENTITY, "")
    try:
        ent_reg = er.async_get(hass)
        nimly_battery = f"{entry.entry_id}_battery"
        for ent in ent_reg.entities.values():
            if ent.unique_id == nimly_battery and not ent.disabled_by:
                battery_entity = ent.entity_id
                break
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
    except Exception:  # noqa: BLE001
        pass

    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "auto_expire": config.get(CONF_AUTO_EXPIRE, True),
        "cleanup_time": config.get(CONF_CLEANUP_TIME, "03:00:00"),
        "lock_entity": lock_entity_id,
        "door_sensor": entry.options.get("door_sensor") or None,
        "battery_entity": battery_entity,
        "auto_lock_enabled": auto_lock_enabled,
        "auto_lock_delay": auto_lock_delay,
    }


@websocket_api.websocket_command({vol.Required("type"): WS_TYPE_TRANSLATIONS})
@websocket_api.async_response
@_guarded("translations_failed")
async def handle_translations(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    """Panel translations for the current language."""
    language = hass.config.language or "en"
    translations_dir = Path(__file__).parent / "panel_translations"
    translation_file = translations_dir / f"{language}.json"

    def _load_translations() -> dict:
        """Load translations from file (runs in executor to avoid blocking)."""
        file_to_load = translation_file
        if not file_to_load.exists():
            file_to_load = translations_dir / "en.json"
        with open(file_to_load, "r", encoding="utf-8") as f:
            return json.load(f)

    translations = await hass.async_add_executor_job(_load_translations)

    # Keep support for both direct panel dictionaries and legacy nested format
    if isinstance(translations, dict) and PANEL_TRANSLATION_KEYS.issubset(translations):
        panel_translations = translations
    elif isinstance(translations.get("panel"), dict):
        panel_translations = translations["panel"]
    else:
        panel_translations = {}

    return {"language": language, "translations": panel_translations}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_SET_AUTO_LOCK,
        vol.Required("enabled"): bool,
        vol.Optional("delay", default=300): int,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
@_guarded("set_auto_lock_failed")
async def handle_set_auto_lock(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    """Enable or disable auto-lock for one lock (stored in its config entry).

    The auto-lock listener in __init__.py reads entry.options live, so the
    change takes effect immediately without a restart.
    """
    enabled = msg["enabled"]
    delay = max(5, int(msg.get("delay", 300)))
    entry = get_entry_data(hass, msg.get("entry_id"))["entry"]
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            OPT_AUTO_LOCK_ENABLED: enabled,
            OPT_AUTO_LOCK_DELAY: delay,
        },
    )
    _LOGGER.info(
        "Auto-lock %s (delay=%ds) saved for %s",
        "enabled" if enabled else "disabled", delay, entry.title,
    )
    return {"success": True, "enabled": enabled, "delay": delay}


@websocket_api.websocket_command(
    {vol.Required("type"): WS_TYPE_ACTIVITY, vol.Optional("entry_id"): str}
)
@websocket_api.async_response
@_guarded("activity_failed")
async def handle_activity(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    """The in-memory activity log of one lock."""
    data = get_entry_data(hass, msg.get("entry_id"))
    return {"entries": data.get("activity_log", [])}


def _zha_cluster(hass: HomeAssistant, msg: dict[str, Any]):
    """DoorLock cluster of the addressed lock, or raise a HomeAssistantError."""
    data = get_entry_data(hass, msg.get("entry_id"))
    zha_ieee = data.get("zha_ieee")
    endpoint_id = data.get("config", {}).get(CONF_ZHA_ENDPOINT_ID, DEFAULT_ZHA_ENDPOINT_ID)
    if not zha_ieee:
        raise HomeAssistantError("Lock is not a ZHA device")
    cluster = get_doorlock_cluster(hass, zha_ieee, endpoint_id)
    if cluster is None:
        raise HomeAssistantError(
            "DoorLock cluster not reachable — interact with the lock first to wake it"
        )
    return cluster


@websocket_api.websocket_command(
    {vol.Required("type"): WS_TYPE_GET_LOCK_SETTINGS, vol.Optional("entry_id"): str}
)
@websocket_api.async_response
@_guarded("read_failed")
async def handle_get_lock_settings(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    """Read current DoorLock settings directly from the Zigbee device."""
    cluster = _zha_cluster(hass, msg)

    attr_ids = [meta["attr_id"] for meta in LOCK_SETTINGS.values()]
    result, _failed = await cluster.read_attributes(attr_ids, allow_cache=False)

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
        except Exception:  # noqa: BLE001
            settings[name] = raw

    return {"settings": settings, "schema": LOCK_SETTINGS}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_SET_LOCK_SETTING,
        vol.Required("setting"): str,
        vol.Required("value"): vol.Any(bool, int),
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
@_guarded("write_failed")
async def handle_set_lock_setting(hass: HomeAssistant, msg: dict[str, Any]) -> dict:
    """Write a single DoorLock attribute to the Zigbee device."""
    setting = msg["setting"]
    if setting not in LOCK_SETTINGS:
        raise HomeAssistantError(f"Unknown setting: {setting}")

    cluster = _zha_cluster(hass, msg)

    meta = LOCK_SETTINGS[setting]
    value = msg["value"]
    if meta["type"] == "bool":
        value = bool(value)
    elif meta["type"] in ("int", "select"):
        value = int(value)

    result = await cluster.write_attributes({setting: value})
    _LOGGER.info("Lock setting %s set to %s (result=%s)", setting, value, result)
    return {"success": True, "setting": setting, "value": value}
