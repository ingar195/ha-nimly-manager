"""Exact-time scheduling for scheduled-start activation and guest expiry.

Schedules a one-off callback (homeassistant.helpers.event.async_track_point_in_time)
per user for their start/expiry instant, instead of relying only on the daily
cleanup scheduler in __init__.py. That daily scheduler and the startup catch-up
still run as a safety net for anything missed while HA was off exactly at a
scheduled moment or while a lock was unreachable.

A user has one slot shared by every lock they can access, so timers are keyed
by slot and act on all of that user's locks at once.
"""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_point_in_time

from .const import DOMAIN, TYPE_GUEST
from .helpers import (
    async_clear_locks,
    async_program_locks,
    auto_expire_enabled,
    failed_locks,
    get_users,
    loaded_entries,
)
from .storage import parse_expiry_datetime, parse_start_datetime

_LOGGER = logging.getLogger(__name__)


def async_cancel_slot(hass: HomeAssistant, slot: int) -> None:
    """Cancel any pending start/expiry timers for a slot."""
    timers = hass.data[DOMAIN].setdefault("slot_timers", {})
    for unsub in timers.pop(slot, {}).values():
        unsub()


def async_schedule_slot(hass: HomeAssistant, slot: int) -> None:
    """(Re)schedule exact-time activation/expiry timers for a slot.

    Cancels any existing timers for the slot first. If a moment has already
    passed (e.g. HA was off), fires that action immediately instead. Expiry is
    only scheduled while at least one lock has auto-expire enabled.
    """
    async_cancel_slot(hass, slot)

    entry = get_users(hass).get(slot)
    if entry is None:
        return

    now = datetime.now()
    slot_timers = {}

    if not entry.activated and entry.start:
        try:
            start_dt = parse_start_datetime(entry.start)
        except (ValueError, TypeError):
            _LOGGER.error("Invalid start date/time for slot %s", slot)
            start_dt = None
        if start_dt is not None:
            if start_dt > now:
                slot_timers["start"] = async_track_point_in_time(
                    hass, _activate_job(hass, slot), start_dt
                )
            else:
                hass.async_create_task(async_activate_slot(hass, slot))

    if entry.type == TYPE_GUEST and entry.expiry and auto_expire_enabled(hass):
        try:
            expiry_dt = parse_expiry_datetime(entry.expiry)
        except (ValueError, TypeError):
            _LOGGER.error("Invalid expiry date/time for slot %s", slot)
            expiry_dt = None
        if expiry_dt is not None:
            if expiry_dt > now:
                slot_timers["expiry"] = async_track_point_in_time(
                    hass, _expire_job(hass, slot), expiry_dt
                )
            else:
                hass.async_create_task(async_expire_slot(hass, slot))

    if slot_timers:
        hass.data[DOMAIN].setdefault("slot_timers", {})[slot] = slot_timers


def async_schedule_all(hass: HomeAssistant) -> None:
    """(Re)schedule timers for every stored user. Call on integration setup."""
    for entry in get_users(hass).list_entries():
        async_schedule_slot(hass, entry.slot)


def async_cancel_all(hass: HomeAssistant) -> None:
    """Cancel every scheduled timer. Call when the last lock unloads."""
    timers = hass.data.get(DOMAIN, {}).get("slot_timers", {})
    for slot in list(timers.keys()):
        async_cancel_slot(hass, slot)


def _activate_job(hass: HomeAssistant, slot: int):
    async def _run(_now) -> None:
        await async_activate_slot(hass, slot)

    return _run


def _expire_job(hass: HomeAssistant, slot: int):
    async def _run(_now) -> None:
        await async_expire_slot(hass, slot)

    return _run


async def async_activate_slot(hass: HomeAssistant, slot: int) -> None:
    """Push a scheduled-start user's PIN to all their locks now that it's time.

    Only marked activated once every lock accepted it; otherwise the daily
    sweep retries (writing a PIN is idempotent).
    """
    if DOMAIN not in hass.data:
        return
    users = get_users(hass)

    entry = users.get(slot)
    if entry is None or entry.activated:
        return
    if not entry.pin:
        _LOGGER.error("Scheduled-start slot %s has no stored PIN — skipping", slot)
        return

    # Locks that aren't loaded (disabled/removed) are skipped; "Sync all locks"
    # brings them up to date when they come back.
    reachable = [l for l in entry.locks if l in loaded_entries(hass)]
    results = await async_program_locks(hass, slot, entry.pin, reachable)
    failed = failed_locks(hass, results)
    if failed:
        _LOGGER.error(
            "Failed to activate scheduled code in slot %s on: %s", slot, failed
        )
        return
    await users.mark_activated(slot)
    _LOGGER.info(
        "Activated scheduled code '%s' in slot %s (start time reached)",
        entry.name, slot,
    )


async def async_expire_slot(hass: HomeAssistant, slot: int) -> None:
    """Remove an expired guest code from all its locks and from the user list.

    Kept (and retried by the daily sweep) if any lock couldn't be cleared —
    the PIN would otherwise stay valid on that lock with no record of it.
    """
    if DOMAIN not in hass.data:
        return
    users = get_users(hass)

    entry = users.get(slot)
    if entry is None:
        return

    reachable = [l for l in entry.locks if l in loaded_entries(hass)]
    results = await async_clear_locks(hass, slot, reachable)
    failed = failed_locks(hass, results)
    if failed:
        _LOGGER.error("Failed to remove expired code from slot %s on: %s", slot, failed)
        return
    await users.remove(slot)
    async_cancel_slot(hass, slot)
    _LOGGER.info(
        "Removed expired code '%s' from slot %s (expiry time reached)",
        entry.name, slot,
    )
