"""Sensor platform for Nimlykoder — auto-lock delay and lock battery."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_ZHA_ENDPOINT_ID, DEFAULT_ZHA_ENDPOINT_ID, OPT_AUTO_LOCK_DELAY

_LOGGER = logging.getLogger(__name__)

BATTERY_PERCENTAGE_ATTR = 0x0021
POWER_CONFIG_CLUSTER_ID = 0x0001


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([
        NimlyAutoLockDelaySensor(entry),
        NimlyBatterySensor(hass, entry),
    ])


class NimlyAutoLockDelaySensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:timer-outline"
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_auto_lock_delay"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Nimlykoder",
            manufacturer="Nimlykoder",
        )

    @property
    def name(self) -> str:
        return "Auto-lock Delay"

    @property
    def native_value(self) -> int:
        return int(self._entry.options.get(OPT_AUTO_LOCK_DELAY, 300))


class NimlyBatterySensor(SensorEntity):
    """Battery sensor driven entirely by ZHA attribute reports.

    No HA polling — the NimlyPowerConfigCluster quirk configures the device
    to push battery_percentage_remaining reports (every 30 min or on 2% change).
    This listener receives those reports and updates the entity state.
    An initial cache read populates the value immediately on startup without
    any radio traffic.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False          # no HA-side polling — zero battery drain
    _attr_icon = "mdi:battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Nimlykoder",
            manufacturer="Nimlykoder",
        )
        self._battery_pct: int | None = None
        self._cluster = None
        self._listener = None

    @property
    def name(self) -> str:
        return "Battery"

    @property
    def native_value(self) -> int | None:
        return self._battery_pct

    @property
    def available(self) -> bool:
        return self._battery_pct is not None

    def _set_battery_from_raw(self, raw) -> None:
        """Convert ZCL raw value (0.5 % units, 200 = 100 %) to integer percent."""
        try:
            self._battery_pct = min(100, round(int(raw) / 2))
        except (TypeError, ValueError):
            pass

    async def async_added_to_hass(self) -> None:
        """Register ZHA cluster listener and do a cache-only initial read."""
        cluster = self._get_power_cluster()
        if cluster is None:
            _LOGGER.debug("NimlyBatterySensor: PowerConfig cluster not available yet")
            return

        self._cluster = cluster

        # --- Listen for attribute reports (push, no radio traffic from our side) ---
        sensor_ref = self

        class _BatteryListener:
            def attribute_updated(self, attr_id, value, timestamp=None):
                if attr_id == BATTERY_PERCENTAGE_ATTR:
                    sensor_ref._set_battery_from_raw(value)
                    sensor_ref.async_write_ha_state()

        self._listener = _BatteryListener()
        cluster.add_listener(self._listener)

        # --- One-time cache read: no radio traffic, just reads zigpy's local cache ---
        try:
            result, _ = await cluster.read_attributes(
                [BATTERY_PERCENTAGE_ATTR], allow_cache=True
            )
            raw = result.get(BATTERY_PERCENTAGE_ATTR) or result.get("battery_percentage_remaining")
            if raw is not None:
                self._set_battery_from_raw(raw)
        except Exception as err:
            _LOGGER.debug("NimlyBatterySensor: cache read failed: %s", err)

    async def async_will_remove_from_hass(self) -> None:
        if self._cluster is not None and self._listener is not None:
            try:
                self._cluster.remove_listener(self._listener)
            except Exception:
                pass

    def _get_power_cluster(self):
        """Find the PowerConfiguration cluster for the Nimly lock."""
        data = self._hass.data.get(DOMAIN, {})
        zha_ieee = data.get("zha_ieee")
        if not zha_ieee:
            return None
        endpoint_id = data.get("config", {}).get(CONF_ZHA_ENDPOINT_ID, DEFAULT_ZHA_ENDPOINT_ID)
        try:
            if "zha" not in self._hass.data:
                return None
            zha_data = self._hass.data["zha"]
            gp = getattr(zha_data, "gateway_proxy", None)
            if gp is None:
                return None
            proxies = getattr(gp, "device_proxies", None)
            if not proxies:
                return None
            ieee_lower = zha_ieee.lower()
            for dev_ieee, proxy in proxies.items():
                if str(dev_ieee).lower() != ieee_lower:
                    continue
                obj = proxy
                for _ in range(4):
                    if hasattr(obj, "endpoints"):
                        for ep_id, ep in obj.endpoints.items():
                            if ep_id != endpoint_id:
                                continue
                            clusters = getattr(ep, "in_clusters", {})
                            if POWER_CONFIG_CLUSTER_ID in clusters:
                                return clusters[POWER_CONFIG_CLUSTER_ID]
                    if hasattr(obj, "device"):
                        obj = obj.device
                    else:
                        break
        except Exception as err:
            _LOGGER.debug("NimlyBatterySensor: error finding cluster: %s", err)
        return None
