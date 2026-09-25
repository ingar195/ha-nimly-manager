"""Standalone tests for the multi-lock user model (no Home Assistant needed).

Loads the real modules from custom_components/nimlykoder with a stubbed
`homeassistant`, so it needs nothing installed. Run either way:

    python tests/test_multilock.py
    python -m pytest tests/test_multilock.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import importlib
import sys
import types
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "nimlykoder"
PKG = "nimlykoder_under_test"


# ---- minimal homeassistant stubs -------------------------------------------
class HomeAssistantError(Exception):
    pass


class Store:
    disk: dict = {}

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return Store.disk.get(self.key)

    async def async_save(self, data):
        Store.disk[self.key] = data


class HomeAssistant:
    pass


timers: list[dict] = []


def async_track_point_in_time(hass, action, when):
    record = {"action": action, "when": when, "cancelled": False}
    timers.append(record)

    def unsub():
        record["cancelled"] = True

    return unsub


def _stub(name: str, **attrs) -> None:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module


def _load():
    _stub("homeassistant")
    _stub("homeassistant.core", HomeAssistant=HomeAssistant)
    _stub("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
    _stub("homeassistant.helpers")
    _stub("homeassistant.helpers.storage", Store=Store)
    _stub("homeassistant.helpers.event", async_track_point_in_time=async_track_point_in_time)
    # A bare package pointing at the real files: __init__.py is never executed.
    package = types.ModuleType(PKG)
    package.__path__ = [str(PACKAGE_DIR)]
    sys.modules[PKG] = package
    mods = {n: importlib.import_module(f"{PKG}.{n}") for n in
            ("const", "storage", "helpers", "scheduler", "users")}
    return types.SimpleNamespace(**mods)


m = _load()


# ---- fakes -----------------------------------------------------------------
class FakeAdapter:
    def __init__(self):
        self.codes: dict[int, str] = {}
        self.fail = False

    async def add_code(self, slot, pin):
        if self.fail:
            raise RuntimeError("offline")
        self.codes[slot] = pin

    async def remove_code(self, slot):
        if self.fail:
            raise RuntimeError("offline")
        self.codes.pop(slot, None)


class ConfigEntry:
    def __init__(self, entry_id, title, entity=None):
        self.entry_id = entry_id
        self.title = title
        self.options = {"lock_entity": entity}


class ConfigEntries:
    def __init__(self, entries):
        self.entries = entries

    def async_entries(self, domain):
        return self.entries

    def async_get_entry(self, entry_id):
        return next((e for e in self.entries if e.entry_id == entry_id), None)


def lock_config(entity, low=1, high=99, guest_min=80, reserved=(1, 2, 3), auto_expire=True):
    return {
        "lock_entity": entity, "slot_min": low, "slot_max": high,
        "guest_slot_min": guest_min, "reserved_slots": list(reserved),
        "auto_expire": auto_expire,
    }


async def make_world(a_config=None, b_config=None):
    """Two loaded locks (A, B) plus a configured-but-unloaded lock C."""
    hass = HomeAssistant()
    hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
    hass.config_entries = ConfigEntries([
        ConfigEntry("A", "Front", "lock.a"),
        ConfigEntry("B", "Back", "lock.b"),
        ConfigEntry("C", "Shed", "lock.c"),
    ])
    Store.disk.clear()
    timers.clear()
    # Legacy data written before multi-lock support: no "locks" key.
    Store.disk["nimlykoder_codes"] = {"version": 1, "entries": {"5": {
        "name": "Old", "type": "permanent", "expiry": None,
        "created": "x", "updated": "x", "pin": "1234",
    }}}
    store = m.storage.NimlykoderStorage(hass)
    await store.async_load(default_lock="A")
    adapters = {"A": FakeAdapter(), "B": FakeAdapter()}
    hass.data = {m.const.DOMAIN: {
        "entries": {
            "A": {"mqtt_adapter": adapters["A"], "config": a_config or lock_config("lock.a")},
            "B": {"mqtt_adapter": adapters["B"], "config": b_config or lock_config("lock.b", high=90)},
        },
        "users": store,
        "slot_timers": {},
    }}
    return hass, store, adapters


async def expect_error(coro, fragment):
    try:
        await coro
    except HomeAssistantError as err:
        assert fragment in str(err), f"{fragment!r} not in {err!s}"
        return
    raise AssertionError(f"expected HomeAssistantError containing {fragment!r}")


# ---- scenarios -------------------------------------------------------------
async def scenario_parsing():
    dt_ = dt.datetime
    assert m.storage.parse_start_datetime("2026-09-20") == dt_(2026, 9, 20, 0, 0, 0)
    assert m.storage.parse_start_datetime("2026-09-20T14:30") == dt_(2026, 9, 20, 14, 30)
    assert m.storage.parse_expiry_datetime("2026-09-20") == dt_(2026, 9, 20, 23, 59, 59)
    assert m.storage.parse_expiry_datetime("2026-09-20T10:00") == dt_(2026, 9, 20, 10, 0)


async def scenario_migration_and_defaults():
    hass, store, ad = await make_world()
    assert store.get(5).locks == ["A"]  # legacy user -> original lock
    # Omitting `locks` targets the original lock only (old automations).
    bob = await m.users.async_add_user(hass, name="Bob", pin_code="4321", code_type="permanent")
    assert bob.locks == ["A"] and ad["A"].codes[bob.slot] == "4321" and bob.slot not in ad["B"].codes


async def scenario_shared_slot_and_ranges():
    hass, store, ad = await make_world()
    amy = await m.users.async_add_user(
        hass, name="Amy", pin_code="1111", code_type="permanent", locks=["lock.a", "B"])
    assert amy.locks == ["A", "B"]
    assert ad["A"].codes[amy.slot] == ad["B"].codes[amy.slot] == "1111"  # same slot on both
    guest = await m.users.async_add_user(
        hass, name="G", pin_code="2222", code_type="guest", expiry="2099-01-01", locks=["A", "B"])
    assert 80 <= guest.slot <= 90  # intersection: guest min 80, B's max 90
    await expect_error(
        m.users.async_add_user(hass, name="N", pin_code="1212", code_type="permanent", locks=[]),
        "at least one")
    await expect_error(
        m.users.async_add_user(hass, name="N", pin_code="1212", code_type="permanent", locks=["nope"]),
        "Unknown lock")


async def scenario_update_locks_pin_and_lookup():
    hass, store, ad = await make_world()
    amy = await m.users.async_add_user(
        hass, name="Amy", pin_code="1111", code_type="permanent", locks=["A", "B"])
    await m.users.async_update_locks(hass, amy.slot, ["B"])
    assert amy.slot not in ad["A"].codes and ad["B"].codes[amy.slot] == "1111"
    await m.users.async_update_locks(hass, amy.slot, ["A", "B"])
    assert ad["A"].codes[amy.slot] == "1111"
    await m.users.async_update_pin(hass, amy.slot, "9999")
    assert ad["A"].codes[amy.slot] == ad["B"].codes[amy.slot] == "9999"
    # Wrong-PIN detection is per lock.
    assert store.find_by_pin("1234", "A") and not store.find_by_pin("1234", "B")


async def scenario_offline_lock_rolls_back():
    hass, store, ad = await make_world()
    ad["B"].fail = True
    await expect_error(
        m.users.async_add_user(hass, name="X", pin_code="5555", code_type="permanent", locks=["A", "B"]),
        "Back")
    assert "5555" not in ad["A"].codes.values()  # the lock that succeeded was rolled back


async def scenario_scheduled_start():
    hass, store, ad = await make_world()
    later = (dt.datetime.now() + dt.timedelta(days=2)).isoformat(timespec="minutes")
    user = await m.users.async_add_user(
        hass, name="Later", pin_code="7777", code_type="permanent", start=later, locks=["A", "B"])
    assert user.activated is False
    assert user.slot not in ad["A"].codes and user.slot not in ad["B"].codes
    assert any(not t["cancelled"] for t in timers)
    await m.scheduler.async_activate_slot(hass, user.slot)
    assert ad["A"].codes[user.slot] == ad["B"].codes[user.slot] == "7777"
    assert store.get(user.slot).activated


async def scenario_resync():
    hass, store, ad = await make_world()
    amy = await m.users.async_add_user(
        hass, name="Amy", pin_code="1111", code_type="permanent", locks=["A", "B"])
    ad["B"].codes.clear()
    ad["B"].codes[5] = "stale"          # user 5 has no access to B
    ad["A"].codes[amy.slot] = "wrong"
    summary = await m.users.async_resync(hass)
    assert ad["A"].codes[amy.slot] == ad["B"].codes[amy.slot] == "1111"
    assert 5 not in ad["B"].codes and ad["A"].codes[5] == "1234"
    assert summary["A"]["failed"] == [] and summary["B"]["failed"] == []
    # One offline lock is reported, the other is still synced.
    ad["B"].fail = True
    ad["A"].codes.clear()
    summary = await m.users.async_resync(hass)
    assert summary["B"]["failed"] and not summary["A"]["failed"]
    assert ad["A"].codes[5] == "1234"


async def scenario_expiry_removal_and_strip():
    hass, store, ad = await make_world()
    guest = await m.users.async_add_user(
        hass, name="G", pin_code="2222", code_type="guest", expiry="2099-01-01", locks=["A", "B"])
    await store.update_expiry(guest.slot, "2000-01-01")
    assert await m.users.async_cleanup_expired(hass) == [guest.slot]
    assert store.get(guest.slot) is None
    assert guest.slot not in ad["A"].codes and guest.slot not in ad["B"].codes
    amy = await m.users.async_add_user(
        hass, name="Amy", pin_code="1111", code_type="permanent", locks=["A", "B"])
    await m.users.async_remove_user(hass, amy.slot)
    assert amy.slot not in ad["A"].codes and amy.slot not in ad["B"].codes
    await store.strip_lock("B")
    assert all("B" not in u.locks for u in store.list_entries())


async def scenario_auto_expire_off():
    off = lock_config("lock.a", auto_expire=False)
    hass, store, ad = await make_world(a_config=off, b_config=lock_config("lock.b", auto_expire=False))
    await m.users.async_add_user(
        hass, name="G", pin_code="2222", code_type="guest", expiry="2099-01-01", locks=["A"])
    # With auto-expire off nothing schedules an expiry timer.
    assert not any(not t["cancelled"] for t in timers)


async def scenario_unloaded_lock():
    """Lock C is configured but failed to load: keep it, never add it."""
    hass, store, ad = await make_world()
    amy = await m.users.async_add_user(
        hass, name="Amy", pin_code="1111", code_type="permanent", locks=["A"])
    await store.update_locks(amy.slot, ["A", "C"])  # she already had access to C
    # Editing other locks keeps C's access untouched.
    updated = await m.users.async_update_locks(hass, amy.slot, ["A", "B", "C"])
    assert updated.locks == ["A", "B", "C"] and ad["B"].codes[amy.slot] == "1111"
    # C can't be newly granted while it isn't loaded.
    bob = await m.users.async_add_user(hass, name="Bob", pin_code="4321", code_type="permanent")
    await expect_error(m.users.async_update_locks(hass, bob.slot, ["A", "C"]), "not loaded")
    # Scheduled actions skip the unloaded lock instead of failing forever.
    await store.update_expiry(amy.slot, "2000-01-01")
    await store.update_locks(amy.slot, ["A", "B", "C"])
    await m.scheduler.async_expire_slot(hass, amy.slot)
    assert store.get(amy.slot) is None


def test_multilock():
    for scenario in (
        scenario_parsing,
        scenario_migration_and_defaults,
        scenario_shared_slot_and_ranges,
        scenario_update_locks_pin_and_lookup,
        scenario_offline_lock_rolls_back,
        scenario_scheduled_start,
        scenario_resync,
        scenario_expiry_removal_and_strip,
        scenario_auto_expire_off,
        scenario_unloaded_lock,
    ):
        asyncio.run(scenario())


if __name__ == "__main__":
    test_multilock()
    print("ALL SCENARIOS OK")
