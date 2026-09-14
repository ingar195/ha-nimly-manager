"""Exact-time scheduling for scheduled-start activation and guest expiry.

Schedules a one-off callback (homeassistant.helpers.event.async_track_point_in_time)
per code for its start/expiry instant, instead of relying only on the daily
cleanup scheduler in __init__.py. That daily scheduler and the startup catch-up
still run as a safety net for anything missed while HA was off exactly at a
scheduled moment.
"""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_point_in_time

from .const import DOMAIN, TYPE_GUEST
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
    passed (e.g. HA was off), fires that action immediately instead.
    """
    async_cancel_slot(hass, slot)

    storage = hass.data[DOMAIN]["storage"]
    entry = storage.get(slot)
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

    if entry.type == TYPE_GUEST and entry.expiry:
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
    """(Re)schedule timers for every stored code. Call on integration setup."""
    storage = hass.data[DOMAIN]["storage"]
    for entry in storage.list_entries():
        async_schedule_slot(hass, entry.slot)


def async_cancel_all(hass: HomeAssistant) -> None:
    """Cancel every scheduled timer. Call on integration unload."""
    timers = hass.data[DOMAIN].get("slot_timers", {})
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
    """Push a scheduled-start code's PIN to the lock now that its time has arrived."""
    data = hass.data.get(DOMAIN)
    if not data:
        return
    storage = data["storage"]
    mqtt_adapter = data["mqtt_adapter"]

    entry = storage.get(slot)
    if entry is None or entry.activated:
        return
    if not entry.pin:
        _LOGGER.error("Scheduled-start slot %s has no stored PIN — skipping", slot)
        return

    try:
        await mqtt_adapter.add_code(slot, entry.pin)
        await storage.mark_activated(slot)
        _LOGGER.info(
            "Activated scheduled code '%s' in slot %s (start time reached)",
            entry.name, slot,
        )
    except Exception as err:
        _LOGGER.error("Failed to activate scheduled code in slot %s: %s", slot, err)


async def async_expire_slot(hass: HomeAssistant, slot: int) -> None:
    """Remove an expired guest code from the lock and storage."""
    data = hass.data.get(DOMAIN)
    if not data:
        return
    storage = data["storage"]
    mqtt_adapter = data["mqtt_adapter"]

    entry = storage.get(slot)
    if entry is None:
        return

    try:
        await mqtt_adapter.remove_code(slot)
        await storage.remove(slot)
        _LOGGER.info(
            "Removed expired code '%s' from slot %s (expiry time reached)",
            entry.name, slot,
        )
    except Exception as err:
        _LOGGER.error("Failed to remove expired code from slot %s: %s", slot, err)

    async_cancel_slot(hass, slot)
