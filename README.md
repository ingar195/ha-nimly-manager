# Nimlykoder - Home Assistant Integration

A complete HACS integration for managing PIN codes on Nimly smart locks via Zigbee2MQTT.

## Features

- ✅ **Persistent Storage** - All PIN codes stored persistently across restarts
- 🔐 **ZHA and Zigbee2MQTT** - Talks to Nimly locks via ZHA or Zigbee2MQTT (picked automatically per lock)
- 🚪 **Multiple Locks** - Any number of locks, one shared list of people, per-person lock access
- 🔄 **Sync All Locks** - One click makes every lock match the shared list
- 🎯 **Auto Slot Assignment** - Automatic slot allocation with reserved slot protection
- ⏰ **Exact Start and Expiry** - Guest codes activate and expire at an exact date and time, with automatic cleanup
- 🖥️ **Sidebar Panel UI** - Beautiful panel interface for managing codes
- 🌐 **Bilingual** - Full support for English and Swedish
- 🔧 **Service Calls** - Control via Home Assistant services and automations
- 📡 **WebSocket API** - Real-time updates via WebSocket commands

## Installation

### Quick Install via HACS (Recommended)

1. Open HACS → Integrations
2. Click three dots (⋮) → Custom repositories
3. Add: `https://github.com/FredrikElliot/ha-nimly-manager` (Integration)
4. Search "Nimlykoder" and install
5. Restart Home Assistant
6. Add integration via Settings → Devices & Services

📖 **[Detailed Installation Guide](examples/INSTALLATION.md)** - Complete step-by-step instructions

### Manual Installation

Copy `custom_components/nimlykoder/` to your Home Assistant's `custom_components` directory and restart.

## Quick Start

1. **Configure Integration**: Settings → Devices & Services → Add Integration → Nimlykoder
2. **Pick the lock**: Choose the lock entity (ZHA or Zigbee2MQTT) and name the entry, e.g. "Front door"
3. **Configure Slots**: Set slot range (0-99) and reserved slots (1-3)
4. **Access Panel**: Click "Nimlykoder" in sidebar
5. **Add First Code**: Click "Add Code" button
6. **More locks**: Repeat steps 1-3 per lock (see [Multiple locks](#multiple-locks))

📘 **[Example Automations](examples/automations.md)** - Ready-to-use automation examples

## Usage

### Sidebar Panel

After installation, you'll find "Nimlykoder" in your Home Assistant sidebar. The panel shows:

- One list of people, shared by all locks
- Slot, name, type (permanent/guest), start, expiry, status and the locks each person can open
- Actions to edit or remove people, and (with several locks) **Sync all locks**
- Status, lock/unlock, battery, door sensor and activity log for the lock selected in the header

#### Adding a Code

1. Click **Add Code**
2. Enter:
   - **Name**: Friendly name for the code
   - **PIN Code**: 4-6 digit PIN
   - **Locks**: Which locks this person can open (several locks only)
   - **Type**: Permanent or Guest
   - **Slot**: Leave empty for auto-assignment or specify a slot number
   - **Expiry**: Required for guest codes. Date, plus an optional time
   - **Start**: Optional date and time. Until then the PIN is not sent to any lock

A person has **one slot, used on every lock they can open**. A date without a time
means start of that day for **Start** and end of that day for **Expiry**.

#### Editing

Click **Edit** to change name, expiry, start, lock access or PIN. Changing lock
access writes the PIN to added locks and clears it from removed ones.

#### Removing a Code

1. Click **Remove** next to a code
2. Confirm the removal

### Services

All services are available in **Developer Tools** → **Services**:

#### `nimlykoder.add_code`

Add a new PIN code.

```yaml
service: nimlykoder.add_code
data:
  name: "Guest User"
  pin_code: "1234"
  type: guest
  expiry: "2026-12-31T11:00"   # date, or date + time for an exact moment
  # Optional:
  # start: "2026-12-28T15:00"  # PIN only reaches the lock(s) at this time
  # slot: 10
  # force: false
  # locks: [lock.front_door, lock.back_door]   # default: the original lock
```

Returns the created entry as a service response. `locks` takes lock entity ids or
config entry ids; leave it out and the code goes to the original (first) lock, so
older automations keep working.

#### `nimlykoder.remove_code`

Remove a person from every lock they can open.

```yaml
service: nimlykoder.remove_code
data:
  slot: 10
```

#### `nimlykoder.update_expiry` / `nimlykoder.update_start`

Change when a code expires / becomes active (date or date + time; leave out to clear).
Moving a start into the future pulls the PIN off the locks again.

```yaml
service: nimlykoder.update_expiry
data:
  slot: 10
  expiry: "2027-01-31T09:00"
```

#### `nimlykoder.update_name` / `nimlykoder.update_pin`

```yaml
service: nimlykoder.update_pin
data:
  slot: 10
  pin_code: "654321"   # written to every lock the person can open
```

#### `nimlykoder.update_locks`

Change which locks a person can open. The PIN is written to added locks and cleared from removed ones.

```yaml
service: nimlykoder.update_locks
data:
  slot: 10
  locks: [lock.front_door]
```

#### `nimlykoder.resync`

Make locks match the shared list (same as **Sync all locks**). Active people get their
PIN written to their locks; everyone else's slot is cleared. Slots that belong to nobody
in the list are never touched. Returns a per-lock summary.

```yaml
service: nimlykoder.resync
data:
  # locks: [lock.back_door]   # default: all locks
```

#### `nimlykoder.list_codes` / `nimlykoder.cleanup_expired` / `nimlykoder.set_auto_lock`

`list_codes` returns all people with their locks; `cleanup_expired` removes expired
guest codes now; `set_auto_lock` takes `enabled`, `delay_seconds` and optional `lock`.

### Multiple locks

Every lock is its own config entry (Settings → Devices & Services → Nimlykoder → Add entry).

- One list of people for all locks; each person can open any subset of them.
- A person uses the **same slot on every lock they can open**, so a slot is unique across locks.
- Name, PIN, type, start and expiry are shared, not per lock.
- The header dropdown (shown with more than one lock) picks which lock's status,
  lock/unlock, auto-lock, settings and activity log you see.
- A lock that fails to load is flagged in the panel. People keep their access to it,
  but it can't be granted until it loads.
- Removing a lock entry removes it from everyone's access.
- Single-lock setups upgrade in place: existing people are assigned to the original lock.
- `nimlykoder_wrong_pin_attempt` events include `entry_id` and `lock_entity`.

### Automations

#### Auto-add guest code on calendar event

```yaml
automation:
  - alias: "Add guest code for visitor"
    trigger:
      - platform: calendar
        event: start
        entity_id: calendar.visitors
    action:
      - service: nimlykoder.add_code
        data:
          name: "{{ trigger.calendar_event.summary }}"
          pin_code: "{{ range(1000, 9999) | random }}"
          type: guest
          expiry: "{{ trigger.calendar_event.end.strftime('%Y-%m-%d') }}"
```

## Architecture

### Components

- **Storage (`storage.py`)**: Persistent storage using Home Assistant's built-in storage system
  - Schema version 1 with migration support
  - Stores slot number, name, type, expiry, timestamps
  - Async operations for all storage access
  
- **MQTT Adapter (`adapters/mqtt_z2m.py`)**: Publishes add/remove commands to Zigbee2MQTT
  - Handles communication with Nimly locks
  - Proper error handling and logging
  - Supports both add and remove operations
  
- **Services (`services.py`)**: Home Assistant service calls for automation
  - `add_code`, `remove_code`, `update_expiry`, `list_codes`
  - Policy enforcement (guest expiry, reserved slots, overwrite protection)
  - Service response support for `list_codes`
  
- **WebSocket API (`websocket.py`)**: Real-time communication with the frontend
  - Commands: list, add, remove, update_expiry, suggest_slots
  - Bidirectional communication for live updates
  - Proper error handling with error codes
  
- **Scheduler (`__init__.py`)**: Daily cleanup of expired guest codes
  - Configurable cleanup time
  - Async job execution
  - Comprehensive logging
  
- **Panel (`panel.py`)**: Custom sidebar panel for UI
  - Registers iframe-based panel
  - Serves static frontend files
  - Integrates with HA sidebar

- **Frontend (`frontend/dist/`)**: Web component-based UI
  - Custom element (nimlykoder-panel)
  - Table view of all codes
  - Modal dialogs for add/edit/remove
  - Real-time updates via WebSocket
  - Uses Lit Element framework

### Data Flow

```
User Action (UI/Service) 
    ↓
WebSocket/Service Handler
    ↓
Policy Enforcement
    ↓
MQTT Adapter → Nimly Lock (via Zigbee2MQTT)
    ↓
Storage Update
    ↓
UI Update (WebSocket response)
```

### Slot Management

- Slots range from 0-99 (configurable)
- Reserved slots (default: 1-3) are protected from auto-assignment
- First available slot is auto-selected when not specified
- Overwrite protection prevents accidental code replacement

### Code Types

- **Permanent**: No expiry date required, remains active indefinitely
- **Guest**: Requires expiry date, automatically removed after expiration

## Localization

The integration automatically uses Swedish if your Home Assistant language is set to Swedish, otherwise English.

To change language:
1. Go to **Profile** (click your username)
2. Change **Language** setting
3. Refresh the page

## Security Considerations

### PIN Code Security

- **PIN codes are transmitted via MQTT**: Ensure your MQTT broker is secured with authentication and TLS
- **Storage encryption**: PIN codes are stored in Home Assistant's storage, protected by file system permissions
- **No PIN code logging**: PIN codes are never logged in Home Assistant logs
- **MQTT QoS 1**: Messages use Quality of Service level 1 for reliable delivery

### Best Practices

1. **Secure MQTT Broker**: 
   - Use authentication (username/password)
   - Enable TLS/SSL encryption
   - Restrict network access to MQTT broker

2. **Reserved Slots**:
   - Keep critical codes (family, emergency) in reserved slots
   - Reserved slots can't be auto-assigned or accidentally overwritten

3. **Overwrite Protection**:
   - Keep enabled to prevent accidental code replacement
   - Only disable when intentionally replacing codes

4. **Guest Code Expiry**:
   - Always set expiry dates for guest codes
   - Enable auto-cleanup to remove expired codes automatically
   - Review guest codes regularly

5. **Access Control**:
   - Only give Home Assistant access to trusted users
   - Use strong Home Assistant passwords
   - Enable two-factor authentication if available

6. **Backup**:
   - Include `.storage/nimlykoder_codes` in your backups
   - Test restore procedures
   - Keep encrypted backups off-site

## Troubleshooting

### Codes not appearing in lock

- Verify MQTT integration is installed and configured
- Check MQTT topic matches your Zigbee2MQTT device
- Check Home Assistant logs for MQTT errors

### Panel not showing

- Verify integration is installed correctly
- Restart Home Assistant
- Clear browser cache

### Expired codes not cleaning up

- Verify "Auto Expire" is enabled in options
- Check cleanup time is set correctly
- Check Home Assistant logs for scheduler errors

## Development

### Project Structure

```
custom_components/nimlykoder/
├── __init__.py           # Main integration setup
├── manifest.json         # Integration metadata
├── const.py             # Constants and defaults
├── config_flow.py       # Configuration flow
├── storage.py           # Persistent storage (shared user list)
├── helpers.py           # Lock lookup, slot ranges, fan-out to locks
├── users.py             # User operations across locks (add, update, resync...)
├── scheduler.py         # Exact-time start/expiry timers
├── services.py          # Service handlers
├── websocket.py         # WebSocket API
├── panel.py             # Panel registration
├── adapters/
│   └── mqtt_z2m.py     # MQTT/Zigbee2MQTT adapter
├── frontend/
│   └── dist/
│       └── nimlykoder-panel.js  # Panel web component
└── translations/
    ├── en.json         # English translations
    └── sv.json         # Swedish translations
tests/
└── test_multilock.py    # Standalone tests, no Home Assistant needed
```

Run the tests with `python tests/test_multilock.py`.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Credits

Developed by Fredrik Elliot

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/FredrikElliot/ha-nimly-manager/issues).
