"""Binary sensor platform for Nimlykoder — exposes auto-lock enabled state."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OPT_AUTO_LOCK_ENABLED


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([NimlyAutoLockBinarySensor(entry)])


class NimlyAutoLockBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "auto_lock_enabled"
    _attr_icon = "mdi:lock-clock"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_auto_lock_enabled"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Nimlykoder",
            manufacturer="Nimlykoder",
        )

    @property
    def name(self) -> str:
        return "Auto-lås aktivert"

    @property
    def is_on(self) -> bool:
        return bool(self._entry.options.get(OPT_AUTO_LOCK_ENABLED, False))

    @property
    def extra_state_attributes(self) -> dict:
        from .const import OPT_AUTO_LOCK_DELAY
        return {
            "delay_seconds": self._entry.options.get(OPT_AUTO_LOCK_DELAY, 300),
        }
