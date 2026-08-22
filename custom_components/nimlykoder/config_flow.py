"""Config flow for Nimlykoder integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_LOCK_ENTITY,
    CONF_DOOR_SENSOR,
    CONF_SLOT_MIN,
    CONF_SLOT_MAX,
    CONF_RESERVED_SLOTS,
    CONF_AUTO_EXPIRE,
    CONF_CLEANUP_TIME,
    CONF_OVERWRITE_PROTECTION,
    CONF_ZHA_ENDPOINT_ID,
    DEFAULT_SLOT_MIN,
    DEFAULT_SLOT_MAX,
    DEFAULT_RESERVED_SLOTS,
    DEFAULT_AUTO_EXPIRE,
    DEFAULT_CLEANUP_TIME,
    DEFAULT_OVERWRITE_PROTECTION,
    DEFAULT_ZHA_ENDPOINT_ID,
)

_LOGGER = logging.getLogger(__name__)


def _parse_reserved_slots(value: Any) -> list[int]:
    """Parse reserved slots from string or list."""
    if isinstance(value, list):
        return [int(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        return [int(x.strip()) for x in value.split(",") if x.strip()]
    return []


def _format_reserved_slots(slots: list[int]) -> str:
    """Format reserved slots list as comma-separated string."""
    return ", ".join(str(x) for x in slots)


class NimlykoderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nimlykoder."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate slot range
            if user_input[CONF_SLOT_MIN] > user_input[CONF_SLOT_MAX]:
                errors["base"] = "invalid_slot_range"
            else:
                # Check if already configured
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()

                # Convert reserved_slots from string to list
                options = dict(user_input)
                options[CONF_RESERVED_SLOTS] = _parse_reserved_slots(
                    user_input.get(CONF_RESERVED_SLOTS, "")
                )

                return self.async_create_entry(
                    title=user_input.get("name", "Nimlykoder"),
                    data={},
                    options=options,
                )

        # Build schema with defaults
        data_schema = vol.Schema(
            {
                vol.Optional("name", default="Nimlykoder"): str,
                vol.Required(CONF_LOCK_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="lock")
                ),
                vol.Optional(CONF_DOOR_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor")
                ),
                vol.Optional(
                    CONF_ZHA_ENDPOINT_ID, default=DEFAULT_ZHA_ENDPOINT_ID
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=255, mode="box")
                ),
                vol.Required(CONF_SLOT_MIN, default=DEFAULT_SLOT_MIN): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=99, mode="box")
                ),
                vol.Required(CONF_SLOT_MAX, default=DEFAULT_SLOT_MAX): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=99, mode="box")
                ),
                vol.Required(
                    CONF_RESERVED_SLOTS,
                    default=_format_reserved_slots(DEFAULT_RESERVED_SLOTS),
                ): str,
                vol.Required(CONF_AUTO_EXPIRE, default=DEFAULT_AUTO_EXPIRE): bool,
                vol.Required(CONF_CLEANUP_TIME, default=DEFAULT_CLEANUP_TIME): selector.TimeSelector(),
                vol.Required(
                    CONF_OVERWRITE_PROTECTION, default=DEFAULT_OVERWRITE_PROTECTION
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return NimlykoderOptionsFlow()


class NimlykoderOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Nimlykoder."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate slot range
            if user_input[CONF_SLOT_MIN] > user_input[CONF_SLOT_MAX]:
                errors["base"] = "invalid_slot_range"
            else:
                # Convert reserved_slots from string to list
                options = dict(user_input)
                options[CONF_RESERVED_SLOTS] = _parse_reserved_slots(
                    user_input.get(CONF_RESERVED_SLOTS, "")
                )
                return self.async_create_entry(title="", data=options)

        # Get current options with safe defaults
        options = self.config_entry.options or {}

        door_sensor = options.get(CONF_DOOR_SENSOR) or None

        # Format reserved_slots for display
        current_reserved = options.get(CONF_RESERVED_SLOTS)
        if current_reserved is None:
            current_reserved = DEFAULT_RESERVED_SLOTS
        if isinstance(current_reserved, list):
            current_reserved = _format_reserved_slots(current_reserved)
        elif not isinstance(current_reserved, str):
            current_reserved = _format_reserved_slots(DEFAULT_RESERVED_SLOTS)

        # Get other options with safe defaults
        lock_entity = options.get(CONF_LOCK_ENTITY) or ""
        slot_min = options.get(CONF_SLOT_MIN)
        if slot_min is None:
            slot_min = DEFAULT_SLOT_MIN
        # Slot 0 is reserved and no longer a valid slot_min — clamp older configs up.
        slot_min = max(int(slot_min), 1)
        slot_max = options.get(CONF_SLOT_MAX)
        if slot_max is None:
            slot_max = DEFAULT_SLOT_MAX
        auto_expire = options.get(CONF_AUTO_EXPIRE)
        if auto_expire is None:
            auto_expire = DEFAULT_AUTO_EXPIRE
        cleanup_time = options.get(CONF_CLEANUP_TIME) or DEFAULT_CLEANUP_TIME
        overwrite_protection = options.get(CONF_OVERWRITE_PROTECTION)
        if overwrite_protection is None:
            overwrite_protection = DEFAULT_OVERWRITE_PROTECTION
        zha_endpoint_id = options.get(CONF_ZHA_ENDPOINT_ID)
        if zha_endpoint_id is None:
            zha_endpoint_id = DEFAULT_ZHA_ENDPOINT_ID

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCK_ENTITY,
                    default=lock_entity,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="lock")
                ),
                vol.Optional(
                    CONF_DOOR_SENSOR,
                    description={"suggested_value": door_sensor},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor")
                ),
                vol.Optional(
                    CONF_ZHA_ENDPOINT_ID,
                    default=zha_endpoint_id,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=255, mode="box")
                ),
                vol.Required(
                    CONF_SLOT_MIN,
                    default=slot_min,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=99, mode="box")
                ),
                vol.Required(
                    CONF_SLOT_MAX,
                    default=slot_max,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=99, mode="box")
                ),
                vol.Required(
                    CONF_RESERVED_SLOTS,
                    default=current_reserved,
                ): str,
                vol.Required(
                    CONF_AUTO_EXPIRE,
                    default=auto_expire,
                ): bool,
                vol.Required(
                    CONF_CLEANUP_TIME,
                    default=cleanup_time,
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_OVERWRITE_PROTECTION,
                    default=overwrite_protection,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=data_schema, errors=errors
        )
