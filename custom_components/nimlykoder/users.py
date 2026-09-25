"""User operations on the shared list, fanned out to every lock a user can open.

Used by both the services and the websocket API. Every function raises
HomeAssistantError on failure; callers only translate that into their own
error format.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import TYPE_GUEST
from .helpers import (
    async_clear_locks,
    async_program_locks,
    auto_expire_enabled,
    check_slot_bounds,
    failed_locks,
    get_entry_data,
    get_users,
    loaded_entries,
    lock_title,
    overwrite_protection,
    resolve_locks,
    slot_range,
)
from .scheduler import (
    async_cancel_slot,
    async_expire_slot,
    async_schedule_slot,
)
from .storage import CodeEntry, parse_expiry_datetime, parse_start_datetime

_LOGGER = logging.getLogger(__name__)


def _validate_pin(pin_code: str) -> None:
    if not pin_code.isdigit() or not 4 <= len(pin_code) <= 6:
        raise HomeAssistantError("PIN code must be 4-6 digits")


def _get_user(hass: HomeAssistant, slot: int) -> CodeEntry:
    entry = get_users(hass).get(slot)
    if entry is None:
        raise HomeAssistantError(f"Slot {slot} not found")
    return entry


def _reachable(hass: HomeAssistant, lock_ids: list[str]) -> list[str]:
    """The subset of `lock_ids` that is currently loaded."""
    loaded = loaded_entries(hass)
    return [l for l in lock_ids if l in loaded]


def suggest_slots(
    hass: HomeAssistant, lock_ids: list[str], code_type: str, count: int
) -> list[int]:
    """Free slots that are valid on every one of `lock_ids`."""
    users = get_users(hass)
    low, high, reserved = slot_range(hass, lock_ids, code_type)
    slots: list[int] = []
    for slot in range(max(low, 1), high + 1):
        if len(slots) >= count:
            break
        if slot in reserved or users.is_slot_occupied(slot):
            continue
        slots.append(slot)
    return slots


async def async_add_user(
    hass: HomeAssistant,
    *,
    name: str,
    pin_code: str,
    code_type: str,
    expiry: str | None = None,
    start: str | None = None,
    slot: int | None = None,
    force: bool = False,
    locks: list[str] | None = None,
) -> CodeEntry:
    """Add a user and program their PIN on every selected lock."""
    users = get_users(hass)
    lock_ids = resolve_locks(hass, locks)

    _validate_pin(pin_code)
    if code_type == TYPE_GUEST and not expiry:
        raise HomeAssistantError("Guest codes must have an expiry date")

    expiry_dt = start_dt = None
    if expiry:
        try:
            expiry_dt = parse_expiry_datetime(expiry)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid expiry date format: {err}") from err
    if start:
        try:
            start_dt = parse_start_datetime(start)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid start date format: {err}") from err
        if expiry_dt and start_dt > expiry_dt:
            raise HomeAssistantError("Start date must be on or before the expiry date")

    if slot is not None:
        check_slot_bounds(hass, slot, lock_ids)
        if users.is_slot_occupied(slot) and (
            not force and overwrite_protection(hass, lock_ids)
        ):
            raise HomeAssistantError(f"Slot {slot} is occupied. Use force=true to overwrite")
    else:
        low, high, reserved = slot_range(hass, lock_ids, code_type)
        slot = users.find_first_free_slot(low, high, reserved)
        if slot is None:
            raise HomeAssistantError("No free slots available")

    previous = users.get(slot)
    pending_start = start_dt is not None and start_dt > datetime.now()

    # Program the locks first; a future start date means the PIN must not
    # reach any lock yet (the scheduler activates it at the exact time).
    if not pending_start:
        results = await async_program_locks(hass, slot, pin_code, lock_ids)
        failed = failed_locks(hass, results)
        if failed:
            succeeded = [l for l, err in results.items() if err is None]
            if succeeded:
                await async_clear_locks(hass, slot, succeeded)
            raise HomeAssistantError(f"Failed to add code to lock: {failed}")

    try:
        entry = await users.add(
            slot, name, code_type, expiry, pin=pin_code, start=start, locks=lock_ids
        )
    except Exception:
        if not pending_start:
            await async_clear_locks(hass, slot, lock_ids)
        raise

    # Overwrote someone on a lock the new user doesn't have: clear it there.
    if previous is not None:
        stale = _reachable(hass, [l for l in previous.locks if l not in lock_ids])
        if stale:
            await async_clear_locks(hass, slot, stale)

    async_schedule_slot(hass, slot)
    _LOGGER.info(
        "Added %s user '%s' in slot %d on %d lock(s)%s",
        code_type, name, slot, len(lock_ids),
        " (pending start)" if pending_start else "",
    )
    return entry


async def async_remove_user(hass: HomeAssistant, slot: int) -> None:
    """Clear the user's slot on all their locks and delete them."""
    entry = _get_user(hass, slot)
    results = await async_clear_locks(hass, slot, _reachable(hass, entry.locks))
    failed = failed_locks(hass, results)
    if failed:
        raise HomeAssistantError(f"Failed to remove code from lock: {failed}")
    await get_users(hass).remove(slot)
    async_cancel_slot(hass, slot)
    _LOGGER.info("Removed user from slot %s", slot)


async def async_update_pin(hass: HomeAssistant, slot: int, pin_code: str) -> CodeEntry:
    """Change a user's PIN on all their locks (pending users: storage only)."""
    entry = _get_user(hass, slot)
    _validate_pin(pin_code)
    if entry.activated:
        results = await async_program_locks(
            hass, slot, pin_code, _reachable(hass, entry.locks)
        )
        failed = failed_locks(hass, results)
        if failed:
            raise HomeAssistantError(f"Failed to update PIN on lock: {failed}")
    return await get_users(hass).update_pin(slot, pin_code)


async def async_update_expiry(
    hass: HomeAssistant, slot: int, expiry: str | None
) -> CodeEntry:
    _get_user(hass, slot)
    if expiry:
        try:
            parse_expiry_datetime(expiry)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid expiry date format: {err}") from err
    entry = await get_users(hass).update_expiry(slot, expiry)
    async_schedule_slot(hass, slot)
    return entry


async def async_update_start(
    hass: HomeAssistant, slot: int, start: str | None
) -> CodeEntry:
    """Reschedule a user's start; pushing it into the future pulls the PIN."""
    entry = _get_user(hass, slot)
    if start:
        try:
            parse_start_datetime(start)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid start date format: {err}") from err

    updated = await get_users(hass).update_start(slot, start)

    if entry.activated and not updated.activated:
        results = await async_clear_locks(hass, slot, _reachable(hass, entry.locks))
        failed = failed_locks(hass, results)
        if failed:
            _LOGGER.error(
                "Failed to pull PIN from slot %s after rescheduling on: %s", slot, failed
            )

    async_schedule_slot(hass, slot)
    return updated


async def async_update_locks(
    hass: HomeAssistant, slot: int, locks: list[str]
) -> CodeEntry:
    """Change which locks a user can open (programs added, clears removed)."""
    entry = _get_user(hass, slot)
    # Locks that failed to load can stay (existing access), but can't be added.
    new_ids = resolve_locks(hass, locks, allow_unloaded=True)
    loaded = loaded_entries(hass)
    added = [l for l in new_ids if l not in entry.locks]
    for lock_id in added:
        if lock_id not in loaded:
            raise HomeAssistantError(f"{lock_title(hass, lock_id)} is not loaded")
    for lock_id in new_ids:
        if lock_id in loaded:
            check_slot_bounds(hass, slot, [lock_id])

    removed = _reachable(hass, [l for l in entry.locks if l not in new_ids])

    if added and entry.activated:
        if not entry.pin:
            raise HomeAssistantError("No stored PIN to program on the new lock(s)")
        results = await async_program_locks(hass, slot, entry.pin, added)
        failed = failed_locks(hass, results)
        if failed:
            succeeded = [l for l, err in results.items() if err is None]
            if succeeded:
                await async_clear_locks(hass, slot, succeeded)
            raise HomeAssistantError(f"Failed to add code to lock: {failed}")

    updated = await get_users(hass).update_locks(slot, new_ids)

    if removed:
        results = await async_clear_locks(hass, slot, removed)
        failed = failed_locks(hass, results)
        if failed:
            raise HomeAssistantError(
                f"Saved, but failed to remove code from lock: {failed} "
                "(use Sync all locks to retry)"
            )
    return updated


async def async_cleanup_expired(hass: HomeAssistant) -> list[int]:
    """Remove every expired guest code from its locks; returns removed slots."""
    users = get_users(hass)
    removed: list[int] = []
    for slot in users.expired_guest_slots():
        await async_expire_slot(hass, slot)
        if users.get(slot) is None:
            removed.append(slot)
    return removed


async def async_resync(
    hass: HomeAssistant, locks: list[str] | None = None
) -> dict[str, dict]:
    """Reconcile locks with the shared user list.

    Per lock (locks in parallel, slots in sequence to spare the radio):
    active users with access get their PIN written; everyone else's slot is
    cleared. Slots that belong to no user are never touched — a lock can't
    be read back, so unknown codes are left alone.
    """
    users = get_users(hass)
    entries = loaded_entries(hass)
    lock_ids = resolve_locks(hass, locks) if locks else list(entries)
    now = datetime.now()
    all_users = users.list_entries()

    summary = {
        lock_id: {"pushed": 0, "removed": 0, "failed": []} for lock_id in lock_ids
    }

    def is_expired(user: CodeEntry) -> bool:
        if user.type != TYPE_GUEST or not user.expiry:
            return False
        try:
            return parse_expiry_datetime(user.expiry) < now
        except ValueError:
            return False

    async def sync_lock(lock_id: str) -> None:
        adapter = get_entry_data(hass, lock_id)["mqtt_adapter"]
        result = summary[lock_id]
        for user in all_users:
            want = lock_id in user.locks and user.activated and not is_expired(user)
            try:
                if want:
                    if not user.pin:
                        raise HomeAssistantError("no stored PIN")
                    await adapter.add_code(user.slot, user.pin)
                    result["pushed"] += 1
                else:
                    await adapter.remove_code(user.slot)
                    result["removed"] += 1
            except Exception as err:  # keep going; report the slot
                _LOGGER.error(
                    "Resync: slot %s on lock %s failed: %s", user.slot, lock_id, err
                )
                result["failed"].append(user.slot)

    await asyncio.gather(*(sync_lock(l) for l in lock_ids))

    # Expired guests were just cleared from the locks; drop them from the list
    # too when every lock is in sync, unless auto-expire is off (manual cleanup).
    if not locks and auto_expire_enabled(hass):
        await async_cleanup_expired(hass)
    return summary
