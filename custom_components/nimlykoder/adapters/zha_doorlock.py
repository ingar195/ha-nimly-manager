"""ZHA adapter for communicating with Nimly locks over the ZCL Door Lock cluster.

Uses direct zigpy cluster method calls (cluster.set_pin_code / cluster.clear_pin_code)
rather than the deprecated zha.issue_zigbee_cluster_command service, which broke in
HA 2024+ when ZHA switched from integer command-ID lookup to name-based lookup
(causing 'tuple index out of range' on command IDs 0x05 and 0x07).

The adapter resolves the zigpy Device via ZHA's get_zha_gateway_proxy helper,
using the lock's HA entity_id to navigate:
  gateway -> entity_ref -> device_proxy -> ZHADevice -> zigpy Device -> endpoint -> cluster

Endpoint discovery tries the configured endpoint_id first (default 11 for Nimly locks,
see zigpy/zha-device-handlers#3095), then falls back to auto-detecting any endpoint
that exposes the DoorLock cluster (0x0101).
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)


class ZhaDoorLockAdapter:
    """Adapter for communicating with Nimly locks via ZHA's Door Lock cluster."""

    def __init__(
        self,
        hass: HomeAssistant,
        ieee: str,
        endpoint_id: int,
        entity_id: str | None = None,
    ) -> None:
        self.hass = hass
        self.ieee = ieee
        self.endpoint_id = endpoint_id
        self.entity_id = entity_id
        _LOGGER.info(
            "[ZhaDoorLockAdapter] Initialized: ieee='%s', endpoint_id=%d, entity_id=%s",
            self.ieee,
            self.endpoint_id,
            self.entity_id,
        )

    def _get_door_lock_cluster(self):
        """Return the zigpy DoorLock cluster, or None if unavailable."""
        from zigpy.zcl.clusters.closures import DoorLock

        if "zha" not in self.hass.config.components:
            _LOGGER.error("[ZhaDoorLockAdapter] ZHA integration not loaded")
            return None

        try:
            from homeassistant.components.zha.helpers import get_zha_gateway_proxy
            gateway = get_zha_gateway_proxy(self.hass)
        except (ImportError, KeyError, ValueError) as err:
            _LOGGER.error("[ZhaDoorLockAdapter] Cannot get ZHA gateway: %s", err)
            return None

        zigpy_device = None

        # Primary: look up via entity_id (most reliable)
        if self.entity_id:
            try:
                entity_ref = gateway.get_entity_reference(self.entity_id)
                if entity_ref and entity_ref.entity_data.device_proxy:
                    device_proxy = entity_ref.entity_data.device_proxy
                    zigpy_device = device_proxy.device.device
                    _LOGGER.debug(
                        "[ZhaDoorLockAdapter] Resolved zigpy device via entity_id '%s'",
                        self.entity_id,
                    )
            except Exception as err:
                _LOGGER.debug(
                    "[ZhaDoorLockAdapter] Entity-id lookup failed (%s), will try IEEE fallback",
                    err,
                )

        # Fallback: scan gateway devices for matching IEEE address
        if zigpy_device is None:
            try:
                inner_gw = getattr(gateway, "gateway", gateway)
                devices = getattr(inner_gw, "devices", {})
                for dev_ieee, zha_dev in devices.items():
                    if str(dev_ieee).lower() == self.ieee.lower():
                        zigpy_device = getattr(
                            getattr(zha_dev, "device", zha_dev), "device", None
                        ) or getattr(zha_dev, "device", None)
                        if zigpy_device is not None:
                            _LOGGER.debug(
                                "[ZhaDoorLockAdapter] Resolved zigpy device via IEEE '%s'",
                                self.ieee,
                            )
                            break
            except Exception as err:
                _LOGGER.debug("[ZhaDoorLockAdapter] IEEE fallback lookup failed: %s", err)

        if zigpy_device is None:
            _LOGGER.error(
                "[ZhaDoorLockAdapter] Could not find zigpy device (ieee=%s, entity_id=%s). "
                "Is the lock paired with ZHA?",
                self.ieee,
                self.entity_id,
            )
            return None

        # Try configured endpoint first, then auto-detect any endpoint with DoorLock cluster
        try:
            if self.endpoint_id in zigpy_device.endpoints:
                ep = zigpy_device.endpoints[self.endpoint_id]
                if DoorLock.cluster_id in ep.in_clusters:
                    _LOGGER.debug(
                        "[ZhaDoorLockAdapter] DoorLock cluster found on configured endpoint %d",
                        self.endpoint_id,
                    )
                    return ep.in_clusters[DoorLock.cluster_id]

            for ep_id, ep in zigpy_device.endpoints.items():
                if ep_id == 0:
                    continue
                if DoorLock.cluster_id in ep.in_clusters:
                    _LOGGER.info(
                        "[ZhaDoorLockAdapter] DoorLock cluster auto-detected on endpoint %d "
                        "(configured endpoint %d had no cluster)",
                        ep_id,
                        self.endpoint_id,
                    )
                    return ep.in_clusters[DoorLock.cluster_id]
        except Exception as err:
            _LOGGER.error("[ZhaDoorLockAdapter] Error locating DoorLock cluster: %s", err)
            return None

        _LOGGER.error(
            "[ZhaDoorLockAdapter] No DoorLock cluster (0x%04X) found on any endpoint of ieee=%s",
            0x0101,
            self.ieee,
        )
        return None

    async def add_code(self, slot: int, pin_code: str, user_type: str = "unrestricted") -> None:
        """Set a PIN code on the lock via the zigpy DoorLock set_pin_code command.

        Args:
            slot: User slot number (ZCL user_id)
            pin_code: PIN code string to program
            user_type: unused — kept for API compatibility; always programs as Unrestricted
        """
        from zigpy.zcl.clusters.closures import DoorLock

        _LOGGER.info(
            "[ZhaDoorLockAdapter] add_code() slot=%d, pin=%s",
            slot,
            "*" * len(pin_code),
        )

        cluster = self._get_door_lock_cluster()
        if cluster is None:
            raise HomeAssistantError(
                "ZHA DoorLock cluster not available — check that ZHA is running and the lock is paired."
            )

        try:
            result = await cluster.set_pin_code(
                slot,
                DoorLock.UserStatus.Enabled,
                DoorLock.UserType.Unrestricted,
                pin_code,
            )
            _LOGGER.info(
                "[ZhaDoorLockAdapter] set_pin_code slot=%d result=%s", slot, result
            )
            if isinstance(result, (list, tuple)):
                status = result[0] if result else 0
            else:
                status = getattr(result, "status", None) or getattr(
                    result, "pin_code_status", 0
                )
            if status and status != 0:
                _LOGGER.warning(
                    "[ZhaDoorLockAdapter] Lock returned non-zero status %s for set_pin_code slot=%d "
                    "(code may still have been set — duplicate/memory-full codes still land on the lock)",
                    status,
                    slot,
                )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.error(
                "[ZhaDoorLockAdapter] set_pin_code failed for slot=%d: %s (type: %s)",
                slot,
                err,
                type(err).__name__,
            )
            raise HomeAssistantError(f"Failed to set PIN via ZHA: {err}") from err

    async def remove_code(self, slot: int) -> None:
        """Clear a PIN code from the lock via the zigpy DoorLock clear_pin_code command.

        Args:
            slot: User slot number (ZCL user_id) to clear
        """
        _LOGGER.info("[ZhaDoorLockAdapter] remove_code() slot=%d", slot)

        cluster = self._get_door_lock_cluster()
        if cluster is None:
            raise HomeAssistantError(
                "ZHA DoorLock cluster not available — check that ZHA is running and the lock is paired."
            )

        try:
            result = await cluster.clear_pin_code(slot)
            _LOGGER.info(
                "[ZhaDoorLockAdapter] clear_pin_code slot=%d result=%s", slot, result
            )
            if isinstance(result, (list, tuple)):
                status = result[0] if result else 0
            else:
                status = getattr(result, "status", 0)
            if status and status != 0:
                _LOGGER.warning(
                    "[ZhaDoorLockAdapter] Lock returned non-zero status %s for clear_pin_code slot=%d",
                    status,
                    slot,
                )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.error(
                "[ZhaDoorLockAdapter] clear_pin_code failed for slot=%d: %s (type: %s)",
                slot,
                err,
                type(err).__name__,
            )
            raise HomeAssistantError(f"Failed to clear PIN via ZHA: {err}") from err

    async def verify_connection(self) -> bool:
        """Return True if ZHA is loaded and the DoorLock cluster is reachable."""
        _LOGGER.debug("[ZhaDoorLockAdapter] verify_connection()")
        cluster = self._get_door_lock_cluster()
        if cluster is not None:
            _LOGGER.info("[ZhaDoorLockAdapter] Connection verified — DoorLock cluster found")
            return True
        _LOGGER.warning(
            "[ZhaDoorLockAdapter] DoorLock cluster NOT found "
            "(ieee=%s, entity_id=%s). "
            "Ensure ZHA is running and the lock is paired.",
            self.ieee,
            self.entity_id,
        )
        return False
