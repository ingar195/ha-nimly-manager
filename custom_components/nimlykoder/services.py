"""Services for Nimlykoder integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_SET_AUTO_LOCK,
    SERVICE_ADD_CODE,
    SERVICE_REMOVE_CODE,
    SERVICE_UPDATE_EXPIRY,
    SERVICE_UPDATE_START,
    SERVICE_UPDATE_NAME,
    SERVICE_UPDATE_PIN,
    SERVICE_UPDATE_LOCKS,
    SERVICE_LIST_CODES,
    SERVICE_CLEANUP_EXPIRED,
    SERVICE_RESYNC,
    TYPE_PERMANENT,
    TYPE_GUEST,
    OPT_AUTO_LOCK_ENABLED,
    OPT_AUTO_LOCK_DELAY,
)
from .helpers import get_entry_data, get_users, resolve_locks
from .users import (
    async_add_user,
    async_cleanup_expired,
    async_remove_user,
    async_resync,
    async_update_expiry,
    async_update_locks,
    async_update_pin,
    async_update_start,
)

_LOGGER = logging.getLogger(__name__)

# Locks are given as config entry ids or lock entity ids. Omitting `locks` (or
# `lock`) means the original lock, so pre-multi-lock automations keep working.
LOCKS_FIELD = vol.All(cv.ensure_list, [cv.string])

# Service schemas
SERVICE_ADD_CODE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("pin_code"): cv.string,
        vol.Required("type"): vol.In([TYPE_PERMANENT, TYPE_GUEST]),
        vol.Optional("expiry"): cv.string,
        vol.Optional("start"): cv.string,
        vol.Optional("slot"): cv.positive_int,
        vol.Optional("force", default=False): cv.boolean,
        vol.Optional("locks"): LOCKS_FIELD,
    }
)

SERVICE_REMOVE_CODE_SCHEMA = vol.Schema(
    {
        vol.Required("slot"): cv.positive_int,
    }
)

SERVICE_UPDATE_EXPIRY_SCHEMA = vol.Schema(
    {
        vol.Required("slot"): cv.positive_int,
        vol.Optional("expiry"): cv.string,
    }
)

SERVICE_UPDATE_START_SCHEMA = vol.Schema(
    {
        vol.Required("slot"): cv.positive_int,
        vol.Optional("start"): cv.string,
    }
)

SERVICE_UPDATE_NAME_SCHEMA = vol.Schema(
    {
        vol.Required("slot"): cv.positive_int,
        vol.Required("name"): cv.string,
    }
)

SERVICE_UPDATE_PIN_SCHEMA = vol.Schema(
    {
        vol.Required("slot"): cv.positive_int,
        vol.Required("pin_code"): cv.string,
    }
)

SERVICE_UPDATE_LOCKS_SCHEMA = vol.Schema(
    {
        vol.Required("slot"): cv.positive_int,
        vol.Required("locks"): LOCKS_FIELD,
    }
)

SERVICE_RESYNC_SCHEMA = vol.Schema(
    {
        vol.Optional("locks"): LOCKS_FIELD,
    }
)

SERVICE_SET_AUTO_LOCK_SCHEMA = vol.Schema(
    {
        vol.Required("enabled"): cv.boolean,
        vol.Optional("delay_seconds", default=300): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=3600)
        ),
        vol.Optional("lock"): cv.string,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Nimlykoder."""

    async def handle_add_code(call: ServiceCall) -> dict:
        entry = await async_add_user(
            hass,
            name=call.data["name"],
            pin_code=call.data["pin_code"],
            code_type=call.data["type"],
            expiry=call.data.get("expiry"),
            start=call.data.get("start"),
            slot=call.data.get("slot"),
            force=call.data.get("force", False),
            locks=call.data.get("locks"),
        )
        return {"entry": entry.to_dict()}

    async def handle_remove_code(call: ServiceCall) -> None:
        await async_remove_user(hass, call.data["slot"])

    async def handle_update_expiry(call: ServiceCall) -> None:
        await async_update_expiry(hass, call.data["slot"], call.data.get("expiry"))

    async def handle_update_start(call: ServiceCall) -> None:
        await async_update_start(hass, call.data["slot"], call.data.get("start"))

    async def handle_update_name(call: ServiceCall) -> None:
        slot = call.data["slot"]
        storage = get_users(hass)
        if storage.get(slot) is None:
            raise HomeAssistantError(f"Slot {slot} not found")
        await storage.update_name(slot, call.data["name"])

    async def handle_update_pin(call: ServiceCall) -> None:
        await async_update_pin(hass, call.data["slot"], call.data["pin_code"])

    async def handle_update_locks(call: ServiceCall) -> dict:
        entry = await async_update_locks(hass, call.data["slot"], call.data["locks"])
        return {"entry": entry.to_dict()}

    async def handle_list_codes(call: ServiceCall) -> dict:
        entries = get_users(hass).list_entries()
        return {"codes": [entry.to_dict() for entry in entries]}

    async def handle_set_auto_lock(call: ServiceCall) -> None:
        """Enable or disable the HA-side auto-lock timer of a lock."""
        (lock_id,) = resolve_locks(hass, [call.data["lock"]] if "lock" in call.data else None)
        entry = get_entry_data(hass, lock_id)["entry"]
        enabled = call.data["enabled"]
        delay = call.data.get("delay_seconds", 300)

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                OPT_AUTO_LOCK_ENABLED: enabled,
                OPT_AUTO_LOCK_DELAY: delay,
            },
        )
        _LOGGER.info(
            "Auto-lock %s (delay=%ds) via service call for %s",
            "enabled" if enabled else "disabled",
            delay,
            entry.title,
        )

    async def handle_cleanup_expired(call: ServiceCall) -> dict:
        removed = await async_cleanup_expired(hass)
        return {"removed": len(removed), "slots": removed}

    async def handle_resync(call: ServiceCall) -> dict:
        return {"locks": await async_resync(hass, call.data.get("locks"))}

    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AUTO_LOCK, handle_set_auto_lock,
        schema=SERVICE_SET_AUTO_LOCK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_CODE, handle_add_code,
        schema=SERVICE_ADD_CODE_SCHEMA, supports_response=True,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_CODE, handle_remove_code,
        schema=SERVICE_REMOVE_CODE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_EXPIRY, handle_update_expiry,
        schema=SERVICE_UPDATE_EXPIRY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_START, handle_update_start,
        schema=SERVICE_UPDATE_START_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_NAME, handle_update_name,
        schema=SERVICE_UPDATE_NAME_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_PIN, handle_update_pin,
        schema=SERVICE_UPDATE_PIN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_LOCKS, handle_update_locks,
        schema=SERVICE_UPDATE_LOCKS_SCHEMA, supports_response=True,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LIST_CODES, handle_list_codes, supports_response=True,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEANUP_EXPIRED, handle_cleanup_expired,
        supports_response=True,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESYNC, handle_resync,
        schema=SERVICE_RESYNC_SCHEMA, supports_response=True,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload services."""
    for service in (
        SERVICE_SET_AUTO_LOCK,
        SERVICE_ADD_CODE,
        SERVICE_REMOVE_CODE,
        SERVICE_UPDATE_EXPIRY,
        SERVICE_UPDATE_START,
        SERVICE_UPDATE_NAME,
        SERVICE_UPDATE_PIN,
        SERVICE_UPDATE_LOCKS,
        SERVICE_LIST_CODES,
        SERVICE_CLEANUP_EXPIRED,
        SERVICE_RESYNC,
    ):
        hass.services.async_remove(DOMAIN, service)
