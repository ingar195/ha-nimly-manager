"""Services for Nimlykoder integration."""
from __future__ import annotations

import logging
from datetime import datetime, date

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_MQTT_TOPIC,
    SERVICE_SET_AUTO_LOCK,
    SERVICE_ADD_CODE,
    SERVICE_REMOVE_CODE,
    SERVICE_UPDATE_EXPIRY,
    SERVICE_UPDATE_NAME,
    SERVICE_UPDATE_PIN,
    SERVICE_LIST_CODES,
    SERVICE_CLEANUP_EXPIRED,
    TYPE_PERMANENT,
    TYPE_GUEST,
    OPT_AUTO_LOCK_ENABLED,
    OPT_AUTO_LOCK_DELAY,
)

_LOGGER = logging.getLogger(__name__)

# Service schemas
SERVICE_ADD_CODE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("pin_code"): cv.string,
        vol.Required("type"): vol.In([TYPE_PERMANENT, TYPE_GUEST]),
        vol.Optional("expiry"): cv.string,
        vol.Optional("slot"): cv.positive_int,
        vol.Optional("force", default=False): cv.boolean,
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

SERVICE_SET_AUTO_LOCK_SCHEMA = vol.Schema(
    {
        vol.Required("enabled"): cv.boolean,
        vol.Optional("delay_seconds", default=300): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=3600)
        ),
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Nimlykoder."""

    async def handle_add_code(call: ServiceCall) -> None:
        """Handle add_code service call."""
        _LOGGER.info("[handle_add_code] Service called with data: %s", call.data)
        
        data = hass.data[DOMAIN]
        storage = data["storage"]
        mqtt_adapter = data["mqtt_adapter"]
        config = data["config"]

        name = call.data["name"]
        pin_code = call.data["pin_code"]
        code_type = call.data["type"]
        expiry = call.data.get("expiry")
        preferred_slot = call.data.get("slot")
        force = call.data.get("force", False)
        
        _LOGGER.info(
            "[handle_add_code] Adding code - name='%s', type=%s, expiry=%s, preferred_slot=%s, force=%s",
            name,
            code_type,
            expiry,
            preferred_slot,
            force,
        )

        # Validate PIN code is 4-6 digits
        if not pin_code.isdigit() or not 4 <= len(pin_code) <= 6:
            _LOGGER.error("[handle_add_code] Invalid PIN code: must be 4-6 digits")
            raise HomeAssistantError("PIN code must be 4-6 digits")

        # Policy enforcement
        if code_type == TYPE_GUEST and not expiry:
            _LOGGER.error("[handle_add_code] Guest codes must have an expiry date")
            raise HomeAssistantError("Guest codes must have an expiry date")

        # Validate expiry format if provided
        if expiry:
            try:
                datetime.fromisoformat(expiry)
                _LOGGER.debug("[handle_add_code] Expiry date validated: %s", expiry)
            except ValueError as err:
                _LOGGER.error("[handle_add_code] Invalid expiry date format: %s", err)
                raise HomeAssistantError(f"Invalid expiry date format: {err}") from err

        # Determine slot
        if preferred_slot is not None:
            slot = preferred_slot
            _LOGGER.debug("[handle_add_code] Using preferred slot: %d", slot)
            # Slot 0 means "no specific user" in decoded lock activity —
            # never allow a real code to occupy it, regardless of slot_min.
            if slot == 0:
                _LOGGER.error("[handle_add_code] Slot 0 is reserved and cannot be used")
                raise HomeAssistantError("Slot 0 is reserved and cannot be used")
            # Check bounds
            if slot < config[
                "slot_min"
            ] or slot > config["slot_max"]:
                _LOGGER.error(
                    "[handle_add_code] Slot %d outside range %d-%d",
                    slot,
                    config['slot_min'],
                    config['slot_max'],
                )
                raise HomeAssistantError(
                    f"Slot {slot} outside configured range "
                    f"({config['slot_min']}-{config['slot_max']})"
                )
            # Check if occupied
            if storage.is_slot_occupied(slot):
                if not force and config.get("overwrite_protection", True):
                    _LOGGER.error(
                        "[handle_add_code] Slot %d is occupied and force=False", slot
                    )
                    raise HomeAssistantError(
                        f"Slot {slot} is occupied. Use force=true to overwrite"
                    )
                _LOGGER.warning("[handle_add_code] Overwriting occupied slot %d", slot)
        else:
            # Auto-select slot
            slot = storage.find_first_free_slot(
                config["slot_min"],
                config["slot_max"],
                config["reserved_slots"],
            )
            if slot is None:
                _LOGGER.error("[handle_add_code] No free slots available")
                raise HomeAssistantError("No free slots available")
            _LOGGER.info("[handle_add_code] Auto-selected slot: %d", slot)

        # Check reserved slots
        if preferred_slot is None and slot in config["reserved_slots"]:
            _LOGGER.error("[handle_add_code] Slot %d is reserved", slot)
            raise HomeAssistantError(f"Slot {slot} is reserved")

        # Send to the lock first (via ZHA or MQTT, depending on configured adapter)
        _LOGGER.info(
            "[handle_add_code] Sending PIN to lock - slot=%d, topic=%s",
            slot,
            config.get(CONF_MQTT_TOPIC, "n/a (ZHA)"),
        )
        try:
            await mqtt_adapter.add_code(slot, pin_code)
            _LOGGER.info("[handle_add_code] Adapter publish successful for slot %d", slot)
        except Exception as err:
            _LOGGER.error(
                "[handle_add_code] Adapter publish failed for slot %d: %s", slot, err
            )
            raise HomeAssistantError(f"Failed to add code to lock: {err}") from err

        # Then store
        try:
            await storage.add(slot, name, code_type, expiry, pin=pin_code)
            _LOGGER.info(
                "[handle_add_code] Successfully added %s code '%s' to slot %d",
                code_type,
                name,
                slot,
            )
        except Exception as err:
            _LOGGER.error(
                "[handle_add_code] Storage failed for slot %d, rolling back lock adapter: %s",
                slot,
                err,
            )
            # Try to clean up the lock adapter if storage fails
            try:
                await mqtt_adapter.remove_code(slot)
                _LOGGER.info("[handle_add_code] Adapter rollback successful")
            except Exception as rollback_err:
                _LOGGER.error(
                    "[handle_add_code] Adapter rollback also failed: %s", rollback_err
                )
            raise

    async def handle_remove_code(call: ServiceCall) -> None:
        """Handle remove_code service call."""
        _LOGGER.info("[handle_remove_code] Service called with data: %s", call.data)
        
        data = hass.data[DOMAIN]
        storage = data["storage"]
        mqtt_adapter = data["mqtt_adapter"]
        config = data["config"]

        slot = call.data["slot"]

        # Check if slot exists
        entry = storage.get(slot)
        if entry is None:
            _LOGGER.error("[handle_remove_code] Slot %d not found in storage", slot)
            raise HomeAssistantError(f"Slot {slot} not found")
        
        _LOGGER.info(
            "[handle_remove_code] Removing code '%s' from slot %d", entry.name, slot
        )

        # Remove from the lock (via ZHA or MQTT, depending on configured adapter)
        _LOGGER.info(
            "[handle_remove_code] Sending remove command to lock - slot=%d, topic=%s",
            slot,
            config.get(CONF_MQTT_TOPIC, "n/a (ZHA)"),
        )
        try:
            await mqtt_adapter.remove_code(slot)
            _LOGGER.info("[handle_remove_code] Adapter remove successful for slot %d", slot)
        except Exception as err:
            raise HomeAssistantError(f"Failed to remove code from lock: {err}") from err

        # Remove from storage
        await storage.remove(slot)
        _LOGGER.info("Removed code from slot %s", slot)

    async def handle_update_expiry(call: ServiceCall) -> None:
        """Handle update_expiry service call."""
        data = hass.data[DOMAIN]
        storage = data["storage"]

        slot = call.data["slot"]
        expiry = call.data.get("expiry")

        # Validate expiry format if provided
        if expiry:
            try:
                datetime.fromisoformat(expiry)
            except ValueError as err:
                raise HomeAssistantError(f"Invalid expiry date format: {err}") from err

        # Update storage
        try:
            await storage.update_expiry(slot, expiry)
            _LOGGER.info("Updated expiry for slot %s to %s", slot, expiry)
        except Exception as err:
            raise HomeAssistantError(f"Failed to update expiry: {err}") from err

    async def handle_list_codes(call: ServiceCall) -> None:
        """Handle list_codes service call."""
        data = hass.data[DOMAIN]
        storage = data["storage"]

        entries = storage.list_entries()
        _LOGGER.info("[handle_list_codes] Listed %d codes", len(entries))

        # Return as service response
        return {"codes": [entry.to_dict() for entry in entries]}

    async def handle_update_name(call: ServiceCall) -> None:
        """Handle update_name service call."""
        _LOGGER.info("[handle_update_name] Service called with data: %s", call.data)
        
        data = hass.data[DOMAIN]
        storage = data["storage"]

        slot = call.data["slot"]
        name = call.data["name"]

        # Check if slot exists
        entry = storage.get(slot)
        if entry is None:
            _LOGGER.error("[handle_update_name] Slot %d not found", slot)
            raise HomeAssistantError(f"Slot {slot} not found")

        # Update storage
        try:
            await storage.update_name(slot, name)
            _LOGGER.info("[handle_update_name] Updated name for slot %d to '%s'", slot, name)
        except Exception as err:
            _LOGGER.error("[handle_update_name] Failed to update name: %s", err)
            raise HomeAssistantError(f"Failed to update name: {err}") from err

    async def handle_update_pin(call: ServiceCall) -> None:
        """Handle update_pin service call - update PIN code for existing slot."""
        _LOGGER.info("[handle_update_pin] Service called for slot %d", call.data["slot"])
        
        data = hass.data[DOMAIN]
        storage = data["storage"]
        mqtt_adapter = data["mqtt_adapter"]
        config = data["config"]

        slot = call.data["slot"]
        pin_code = call.data["pin_code"]

        # Check if slot exists
        entry = storage.get(slot)
        if entry is None:
            _LOGGER.error("[handle_update_pin] Slot %d not found", slot)
            raise HomeAssistantError(f"Slot {slot} not found")

        # Validate PIN code is 4-6 digits
        if not pin_code.isdigit() or not 4 <= len(pin_code) <= 6:
            _LOGGER.error("[handle_update_pin] Invalid PIN code format")
            raise HomeAssistantError("PIN code must be 4-6 digits")

        # Send new PIN to the lock (via ZHA or MQTT, depending on configured adapter)
        _LOGGER.info(
            "[handle_update_pin] Sending new PIN to lock for slot %d",
            slot,
        )
        try:
            await mqtt_adapter.add_code(slot, pin_code)
            _LOGGER.info("[handle_update_pin] Successfully updated PIN for slot %d", slot)
        except Exception as err:
            _LOGGER.error("[handle_update_pin] Adapter publish failed: %s", err)
            raise HomeAssistantError(f"Failed to update PIN on lock: {err}") from err

        # Persist the new PIN in storage
        try:
            await storage.update_pin(slot, pin_code)
        except Exception as err:
            _LOGGER.warning("[handle_update_pin] Failed to persist PIN in storage: %s", err)

    async def handle_set_auto_lock(call: ServiceCall) -> None:
        """Enable or disable the HA-side auto-lock timer."""
        data = hass.data[DOMAIN]
        entry = data["entry"]
        enabled = call.data["enabled"]
        delay = call.data.get("delay_seconds", 300)

        new_options = {
            **entry.options,
            OPT_AUTO_LOCK_ENABLED: enabled,
            OPT_AUTO_LOCK_DELAY: delay,
        }
        hass.config_entries.async_update_entry(entry, options=new_options)
        _LOGGER.info(
            "Auto-lock %s (delay=%ds) via service call",
            "enabled" if enabled else "disabled",
            delay,
        )

    async def handle_cleanup_expired(call: ServiceCall) -> None:
        """Handle cleanup_expired service call - manually trigger expired code cleanup."""
        _LOGGER.info("[handle_cleanup_expired] Manual cleanup triggered")
        
        data = hass.data[DOMAIN]
        storage = data["storage"]
        mqtt_adapter = data["mqtt_adapter"]
        config = data["config"]

        today = date.today()
        expired_slots = storage.expired_guest_slots(today)

        if not expired_slots:
            _LOGGER.info("[handle_cleanup_expired] No expired guest codes to clean up")
            return {"removed": 0, "slots": []}

        _LOGGER.info(
            "[handle_cleanup_expired] Found %d expired guest codes: %s",
            len(expired_slots),
            expired_slots,
        )
        removed_slots = []

        for slot in expired_slots:
            try:
                entry = storage.get(slot)
                name = entry.name if entry else f"Slot {slot}"

                _LOGGER.info(
                    "[handle_cleanup_expired] Removing expired code '%s' from slot %d",
                    name,
                    slot,
                )

                # Remove from the lock
                await mqtt_adapter.remove_code(slot)
                # Remove from storage
                await storage.remove(slot)

                _LOGGER.info(
                    "[handle_cleanup_expired] Successfully removed expired code '%s' from slot %d",
                    name,
                    slot,
                )
                removed_slots.append(slot)
            except Exception as err:
                _LOGGER.error(
                    "[handle_cleanup_expired] Failed to remove expired code from slot %d: %s",
                    slot,
                    err,
                )

        _LOGGER.info(
            "[handle_cleanup_expired] Cleanup completed: removed %d/%d codes",
            len(removed_slots),
            len(expired_slots),
        )
        return {"removed": len(removed_slots), "slots": removed_slots}

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AUTO_LOCK,
        handle_set_auto_lock,
        schema=SERVICE_SET_AUTO_LOCK_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_CODE,
        handle_add_code,
        schema=SERVICE_ADD_CODE_SCHEMA,
        supports_response=True,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_CODE,
        handle_remove_code,
        schema=SERVICE_REMOVE_CODE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_EXPIRY,
        handle_update_expiry,
        schema=SERVICE_UPDATE_EXPIRY_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_NAME,
        handle_update_name,
        schema=SERVICE_UPDATE_NAME_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_PIN,
        handle_update_pin,
        schema=SERVICE_UPDATE_PIN_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_CODES,
        handle_list_codes,
        supports_response=True,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEANUP_EXPIRED,
        handle_cleanup_expired,
        supports_response=True,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload services."""
    hass.services.async_remove(DOMAIN, SERVICE_SET_AUTO_LOCK)
    hass.services.async_remove(DOMAIN, SERVICE_ADD_CODE)
    hass.services.async_remove(DOMAIN, SERVICE_REMOVE_CODE)
    hass.services.async_remove(DOMAIN, SERVICE_UPDATE_EXPIRY)
    hass.services.async_remove(DOMAIN, SERVICE_UPDATE_NAME)
    hass.services.async_remove(DOMAIN, SERVICE_UPDATE_PIN)
    hass.services.async_remove(DOMAIN, SERVICE_LIST_CODES)
    hass.services.async_remove(DOMAIN, SERVICE_CLEANUP_EXPIRED)
