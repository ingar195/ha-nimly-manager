"""Storage management for Nimlykoder integration."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.exceptions import HomeAssistantError

from .const import STORAGE_KEY, STORAGE_VERSION, TYPE_PERMANENT, TYPE_GUEST

_LOGGER = logging.getLogger(__name__)


@dataclass
class CodeEntry:
    """Represents a PIN code entry."""

    slot: int
    name: str
    type: str
    expiry: str | None
    created: str
    updated: str
    pin: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Excludes `pin` — it must never leave storage.py. Nothing outside this
        module (services, websocket, panel) should ever see a stored PIN.
        """
        d = asdict(self)
        d.pop("pin", None)
        return d

    @staticmethod
    def from_dict(slot: int, data: dict[str, Any]) -> CodeEntry:
        """Create from dictionary."""
        return CodeEntry(
            slot=slot,
            name=data["name"],
            type=data["type"],
            expiry=data.get("expiry"),
            created=data["created"],
            updated=data["updated"],
            pin=data.get("pin"),
        )


class NimlykoderStorage:
    """Manage persistent storage for PIN codes."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Load data from storage."""
        data = await self._store.async_load()
        if data is None:
            self._data = {}
        else:
            # Handle migration if needed
            if data.get("version", 1) == STORAGE_VERSION:
                self._data = data.get("entries", {})
            else:
                _LOGGER.warning("Unknown storage version, resetting data")
                self._data = {}

    async def async_save(self) -> None:
        """Save data to storage."""
        await self._store.async_save(
            {
                "version": STORAGE_VERSION,
                "entries": self._data,
            }
        )

    def list_entries(self) -> list[CodeEntry]:
        """List all entries."""
        entries = []
        for slot_str, data in self._data.items():
            slot = int(slot_str)
            entries.append(CodeEntry.from_dict(slot, data))
        return sorted(entries, key=lambda e: e.slot)

    def get(self, slot: int) -> CodeEntry | None:
        """Get entry by slot."""
        slot_str = str(slot)
        if slot_str not in self._data:
            return None
        return CodeEntry.from_dict(slot, self._data[slot_str])

    async def add(
        self,
        slot: int,
        name: str,
        code_type: str,
        expiry: str | None = None,
        pin: str | None = None,
    ) -> CodeEntry:
        """Add a new entry."""
        now = datetime.now().isoformat()
        slot_str = str(slot)

        # Validate type and expiry
        if code_type == TYPE_GUEST and expiry is None:
            raise HomeAssistantError("Guest codes must have an expiry date")

        entry_data = {
            "name": name,
            "type": code_type,
            "expiry": expiry,
            "created": now,
            "updated": now,
            "pin": pin,
        }

        self._data[slot_str] = entry_data
        await self.async_save()

        return CodeEntry.from_dict(slot, entry_data)

    async def remove(self, slot: int) -> None:
        """Remove an entry."""
        slot_str = str(slot)
        if slot_str in self._data:
            del self._data[slot_str]
            await self.async_save()

    async def update_expiry(self, slot: int, expiry: str | None) -> CodeEntry:
        """Update expiry date."""
        slot_str = str(slot)
        if slot_str not in self._data:
            raise HomeAssistantError(f"Slot {slot} not found")

        self._data[slot_str]["expiry"] = expiry
        self._data[slot_str]["updated"] = datetime.now().isoformat()
        await self.async_save()

        return CodeEntry.from_dict(slot, self._data[slot_str])

    async def update_pin(self, slot: int, pin: str) -> CodeEntry:
        """Update the stored PIN for an existing entry."""
        slot_str = str(slot)
        if slot_str not in self._data:
            raise HomeAssistantError(f"Slot {slot} not found")

        self._data[slot_str]["pin"] = pin
        self._data[slot_str]["updated"] = datetime.now().isoformat()
        await self.async_save()

        return CodeEntry.from_dict(slot, self._data[slot_str])

    def find_by_pin(self, pin: str, today: date | None = None) -> CodeEntry | None:
        """Find a currently-valid entry whose stored PIN matches.

        Expired guest codes don't count as a match, so a PIN typed on a
        code that's since expired is treated the same as an unknown PIN.
        """
        today = today or date.today()
        for slot_str, data in self._data.items():
            if data.get("pin") != pin:
                continue
            entry = CodeEntry.from_dict(int(slot_str), data)
            if entry.type == TYPE_GUEST and entry.expiry:
                try:
                    if datetime.fromisoformat(entry.expiry).date() < today:
                        continue
                except (ValueError, TypeError):
                    pass
            return entry
        return None

    async def update_name(self, slot: int, name: str) -> CodeEntry:
        """Update name for a code entry."""
        slot_str = str(slot)
        if slot_str not in self._data:
            raise HomeAssistantError(f"Slot {slot} not found")

        if not name or not name.strip():
            raise HomeAssistantError("Name cannot be empty")

        self._data[slot_str]["name"] = name.strip()
        self._data[slot_str]["updated"] = datetime.now().isoformat()
        await self.async_save()

        return CodeEntry.from_dict(slot, self._data[slot_str])

    def find_first_free_slot(
        self, slot_min: int, slot_max: int, reserved_slots: list[int]
    ) -> int | None:
        """Find first available slot outside reserved range.

        Slot 0 is never returned — it's reserved to mean "no specific user"
        in decoded lock activity, regardless of configured slot_min.
        """
        for slot in range(max(slot_min, 1), slot_max + 1):
            if slot in reserved_slots:
                continue
            if str(slot) not in self._data:
                return slot
        return None

    def expired_guest_slots(self, today: date) -> list[int]:
        """Get list of expired guest code slots."""
        expired = []
        for slot_str, data in self._data.items():
            if data["type"] == TYPE_GUEST and data.get("expiry"):
                try:
                    expiry_date = datetime.fromisoformat(data["expiry"]).date()
                    if expiry_date < today:
                        expired.append(int(slot_str))
                except (ValueError, TypeError):
                    _LOGGER.error("Invalid expiry date for slot %s", slot_str)
        return expired

    def is_slot_occupied(self, slot: int) -> bool:
        """Check if slot is occupied."""
        return str(slot) in self._data
