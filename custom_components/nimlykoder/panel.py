"""Panel registration for Nimlykoder integration."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.frontend import async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PANEL_NAME, PANEL_TITLE, PANEL_ICON

_LOGGER = logging.getLogger(__name__)


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Nimlykoder panel."""
    try:
        # Register URL for serving the panel frontend files
        frontend_path = Path(__file__).parent / "frontend" / "dist"

        # Register static path for frontend files
        await hass.http.async_register_static_paths(
            [StaticPathConfig(f"/{DOMAIN}_panel", str(frontend_path), cache_headers=False)]
        )

        # Register the custom panel — version bump forces browser cache invalidation
        _PANEL_VERSION = "20260816-2"
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name="nimlykoder-panel",
            frontend_url_path=PANEL_NAME,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=f"/{DOMAIN}_panel/nimlykoder-panel.js?v={_PANEL_VERSION}",
            embed_iframe=False,
            require_admin=False,
        )

        _LOGGER.info("Registered Nimlykoder panel")

    except Exception as err:
        _LOGGER.error("Failed to register panel: %s", err)


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister the Nimlykoder panel."""
    try:
        async_remove_panel(hass, PANEL_NAME)
        _LOGGER.info("Unregistered Nimlykoder panel")
    except Exception as err:
        _LOGGER.error("Failed to unregister panel: %s", err)
