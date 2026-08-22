"""ZHA cluster access helpers — shared between __init__ and websocket."""
from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_ZHA_DOMAIN = "zha"
_DOORLOCK_CLUSTER_ID = 0x0101

# Writable DoorLock attributes exposed to the panel.
# Each entry: (attr_name, attr_id, value_type, min, max)
LOCK_SETTINGS = {
    "sound_volume": {
        "attr_id": 0x0024,
        "type": "select",
        "options": {0: "silent", 1: "low", 2: "high"},
    },
    "enable_one_touch_locking": {
        "attr_id": 0x0029,
        "type": "bool",
    },
    "enable_privacy_mode_button": {
        "attr_id": 0x002B,
        "type": "bool",
    },
    "wrong_code_attempt_limit": {
        "attr_id": 0x0030,
        "type": "int",
        "min": 1,
        "max": 10,
    },
    "user_code_temporary_disable_time": {
        "attr_id": 0x0031,
        "type": "int",
        "min": 0,
        "max": 254,
    },
}


def get_doorlock_cluster(hass: HomeAssistant, zha_ieee: str, endpoint_id: int):
    """Return the DoorLock ZCL cluster for the given ZHA device, or None."""
    try:
        if _ZHA_DOMAIN not in hass.data:
            return None
        zha_data = hass.data[_ZHA_DOMAIN]
        gp = getattr(zha_data, "gateway_proxy", None)
        if gp is None:
            return None
        device_proxies = getattr(gp, "device_proxies", None)
        if not device_proxies:
            return None
        ieee_lower = str(zha_ieee).lower()
        for dev_ieee, proxy in device_proxies.items():
            if str(dev_ieee).lower() != ieee_lower:
                continue
            obj = proxy
            for _ in range(4):
                if hasattr(obj, "endpoints"):
                    for ep_id, ep in obj.endpoints.items():
                        if ep_id != endpoint_id:
                            continue
                        clusters = getattr(ep, "in_clusters", {})
                        if _DOORLOCK_CLUSTER_ID in clusters:
                            return clusters[_DOORLOCK_CLUSTER_ID]
                if hasattr(obj, "device"):
                    obj = obj.device
                else:
                    break
    except Exception as exc:
        _LOGGER.debug("Exception in get_doorlock_cluster: %s", exc)
    return None
