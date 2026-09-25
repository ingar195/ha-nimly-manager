"""Helpers for the multi-lock model: one shared user list, N locks.

Runtime layout of hass.data[DOMAIN]:
    {"entries": {entry_id: <per-lock data dict>}, "users": NimlykoderStorage,
     "slot_timers": {...}}
Each per-lock data dict also carries "storage" pointing at the shared user list.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_LOCK_ENTITY,
    CONF_SLOT_MIN,
    CONF_SLOT_MAX,
    CONF_GUEST_SLOT_MIN,
    CONF_AUTO_EXPIRE,
    DEFAULT_GUEST_SLOT_MIN,
    TYPE_GUEST,
)


def loaded_entries(hass: HomeAssistant) -> dict[str, dict]:
    """Per-lock data dicts of all currently loaded lock entries."""
    return hass.data.get(DOMAIN, {}).get("entries", {})


def get_users(hass: HomeAssistant):
    """The shared user list."""
    users = hass.data.get(DOMAIN, {}).get("users")
    if users is None:
        raise HomeAssistantError("Nimlykoder is not loaded")
    return users


def default_lock_id(hass: HomeAssistant) -> str:
    """The original (first-configured) lock among the loaded ones."""
    entries = loaded_entries(hass)
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        if config_entry.entry_id in entries:
            return config_entry.entry_id
    raise HomeAssistantError("Nimlykoder is not loaded")


def get_entry_data(hass: HomeAssistant, entry_id: str | None = None) -> dict:
    """Per-lock data for `entry_id` (default: the original lock)."""
    entries = loaded_entries(hass)
    if entry_id is None:
        entry_id = default_lock_id(hass)
    data = entries.get(entry_id)
    if data is None:
        raise HomeAssistantError(f"Unknown lock: {entry_id}")
    return data


def lock_title(hass: HomeAssistant, entry_id: str) -> str:
    """Human-readable name of a lock for error messages."""
    config_entry = hass.config_entries.async_get_entry(entry_id)
    return config_entry.title if config_entry else entry_id


def resolve_locks(
    hass: HomeAssistant, locks: list[str] | None, allow_empty: bool = False
) -> list[str]:
    """Turn a list of entry_ids and/or lock entity_ids into entry_ids.

    None/empty falls back to the original lock (so callers that never heard
    of multiple locks keep working) unless `allow_empty` is set.
    """
    entries = loaded_entries(hass)
    if locks is None:
        return [default_lock_id(hass)]
    if not locks:
        # An explicit empty list is a mistake (unticked every lock), not "default".
        if allow_empty:
            return []
        raise HomeAssistantError("Select at least one lock")
    by_entity = {
        d["config"][CONF_LOCK_ENTITY]: eid for eid, d in entries.items()
    }
    resolved: list[str] = []
    for lock in locks:
        entry_id = lock if lock in entries else by_entity.get(lock)
        if entry_id is None:
            raise HomeAssistantError(f"Unknown lock: {lock}")
        if entry_id not in resolved:
            resolved.append(entry_id)
    return resolved


def auto_expire_enabled(hass: HomeAssistant) -> bool:
    """True if any loaded lock has automatic expiry cleanup enabled."""
    return any(
        d["config"].get(CONF_AUTO_EXPIRE, True) for d in loaded_entries(hass).values()
    )


def slot_range(
    hass: HomeAssistant, lock_ids: list[str], code_type: str
) -> tuple[int, int, list[int]]:
    """Slot range valid on *all* given locks (a user has one slot everywhere)."""
    low, high, reserved = 1, 10**6, set()
    for lock_id in lock_ids:
        config = get_entry_data(hass, lock_id)["config"]
        if code_type == TYPE_GUEST:
            low = max(low, config.get(CONF_GUEST_SLOT_MIN, DEFAULT_GUEST_SLOT_MIN))
        else:
            low = max(low, config[CONF_SLOT_MIN])
        high = min(high, config[CONF_SLOT_MAX])
        reserved.update(config["reserved_slots"])
    if low > high:
        raise HomeAssistantError(
            "The selected locks have no slot range in common"
        )
    return low, high, sorted(reserved)


def check_slot_bounds(hass: HomeAssistant, slot: int, lock_ids: list[str]) -> None:
    """Raise if `slot` is outside the configured range of any selected lock."""
    if slot == 0:
        raise HomeAssistantError("Slot 0 is reserved and cannot be used")
    for lock_id in lock_ids:
        config = get_entry_data(hass, lock_id)["config"]
        if slot < config[CONF_SLOT_MIN] or slot > config[CONF_SLOT_MAX]:
            raise HomeAssistantError(
                f"Slot {slot} outside configured range "
                f"({config[CONF_SLOT_MIN]}-{config[CONF_SLOT_MAX]}) "
                f"of {lock_title(hass, lock_id)}"
            )


def overwrite_protection(hass: HomeAssistant, lock_ids: list[str]) -> bool:
    """True if any selected lock has overwrite protection on."""
    return any(
        get_entry_data(hass, l)["config"].get("overwrite_protection", True)
        for l in lock_ids
    )


async def _run_on_locks(
    hass: HomeAssistant,
    lock_ids: list[str],
    action: Callable[[object], Awaitable],
) -> dict[str, Exception | None]:
    """Run `action(adapter)` on every lock in parallel; map lock -> error/None."""
    entries = loaded_entries(hass)

    async def one(lock_id: str) -> None:
        data = entries.get(lock_id)
        if data is None:
            raise HomeAssistantError("lock is not loaded")
        await action(data["mqtt_adapter"])

    results = await asyncio.gather(
        *(one(l) for l in lock_ids), return_exceptions=True
    )
    return {
        lock_id: (result if isinstance(result, Exception) else None)
        for lock_id, result in zip(lock_ids, results)
    }


async def async_program_locks(
    hass: HomeAssistant, slot: int, pin: str, lock_ids: list[str]
) -> dict[str, Exception | None]:
    """Write a PIN into `slot` on every given lock."""
    return await _run_on_locks(hass, lock_ids, lambda a: a.add_code(slot, pin))


async def async_clear_locks(
    hass: HomeAssistant, slot: int, lock_ids: list[str]
) -> dict[str, Exception | None]:
    """Clear `slot` on every given lock."""
    return await _run_on_locks(hass, lock_ids, lambda a: a.remove_code(slot))


def failed_locks(hass: HomeAssistant, results: dict[str, Exception | None]) -> str:
    """'Front door (timeout), Back door (...)' for the failed locks, or ''."""
    return ", ".join(
        f"{lock_title(hass, lock_id)} ({err})"
        for lock_id, err in results.items()
        if err is not None
    )
