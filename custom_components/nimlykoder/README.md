# Nimlykoder

Home Assistant custom integration for administrasjon av PIN-koder, fingeravtrykk og RFID-tilganger på Nimly-låsen over ZHA/Zigbee.

## Funksjoner

- PIN-kodeadministrasjon (permanent og gjest med utløpsdato)
- Aktivitetslogg med kildeidentifikasjon (kode, fingeravtrykk, RFID, manuell, feil kode)
- HA-styrt auto-lås med konfigurerbar forsinkelse
- Valgfri dørsensor vist i panelet
- ZHA-quirk som deaktiverer hardware auto-lås og aktiverer batteristatus
- HA-entiteter for auto-lås-status lesbart fra Node-RED og automatiseringer
- Node-RED-integrasjon via `nimlykoder.set_auto_lock`-tjenesten

---

## Installasjon

1. Kopier `nimlykoder/`-mappen til `/config/custom_components/`
2. Start Home Assistant på nytt
3. Innstillinger → Enheter og tjenester → Legg til integrasjon → «Nimlykoder»
4. Panelet dukker opp i sidemenyen

---

## ZHA Quirk (NimlyCodePRO)

Løser to problemer: deaktiverer hardware auto-lås og aktiverer batteristatus.

```yaml
# configuration.yaml
zha:
  custom_quirks_path: /config/custom_zha_quirks/
```

Kopier `custom_zha_quirks/nimlycodepro.py` til `/config/custom_zha_quirks/`, start på nytt, og gå til Innstillinger → Enheter → NimlyCodePRO → **Rekonfigurer**.

> Batterisensoren vises ikke før enheten er rekonfigurert etter quirk-installasjon.

---

## Konfigurasjon

| Felt | Påkrevd | Standard | Beskrivelse |
|---|---|---|---|
| `lock_entity` | ✅ | — | Lås-entitet fra ZHA |
| `door_sensor` | — | — | Valgfri binær sensor for dørstatus (vises i topplinja) |
| `zha_endpoint_id` | — | `11` | ZHA endpoint-ID. NimlyCodePRO bruker 11 |
| `slot_min` | ✅ | `0` | Laveste kodespor |
| `slot_max` | ✅ | `99` | Høyeste kodespor |
| `reserved_slots` | — | `1,2,3` | Spor som aldri overskrives automatisk |
| `auto_expire` | — | `true` | Slett utløpte gjestekoder automatisk |
| `cleanup_time` | — | `03:00:00` | Tidspunkt for daglig opprydning |
| `overwrite_protection` | — | `true` | Hindrer overskriving uten `force: true` |

---

## HA-entiteter

Opprettes automatisk — leser fra HA-minne, ingen Zigbee-trafikk:

| Entitet | Verdier | Beskrivelse |
|---|---|---|
| `binary_sensor.nimlykoder_auto_lock_enabled` | `on` / `off` | Om auto-lås er aktivert. Har `delay_seconds` som attributt |
| `sensor.nimlykoder_auto_lock_delay` | int (sekunder) | Forsinkelse for auto-lås |

---

## Aktivitetslogg

Loggen vises i panelet og oppdateres automatisk hvert 30. sekund. Den er persistent og overlever omstart. Maks 200 hendelser lagres i `.storage/nimlykoder_activity`.

Hendelsestyper: lås/opplåsing via kode, fingeravtrykk, RFID, manuell, Zigbee, auto-lås, og **feil kode** (vises med rød prikk).

---

## Auto-lås

HA-styrt — overvåker lås-entitetens tilstand og sender lås-kommando etter valgt forsinkelse.

```yaml
service: nimlykoder.set_auto_lock
data:
  enabled: true
  delay_seconds: 30   # 5–3600 sekunder
```

```yaml
service: nimlykoder.set_auto_lock
data:
  enabled: false
```

---

## HA-tjenester

### `nimlykoder.set_auto_lock`
| Parameter | Type | Beskrivelse |
|---|---|---|
| `enabled` | bool ✅ | Slå på/av |
| `delay_seconds` | int (5–3600) | Forsinkelse. Standard: 300 |

### `nimlykoder.add_code`
| Parameter | Type | Beskrivelse |
|---|---|---|
| `name` | str ✅ | Brukernavn |
| `pin_code` | str ✅ | 4–6 siffers kode |
| `type` | str ✅ | `permanent` eller `guest` |
| `expiry` | date | Utløpsdato YYYY-MM-DD (påkrevd for guest) |
| `slot` | int | Foretrukket spor (auto-valgt om utelatt) |
| `force` | bool | Overskriv opptatt spor. Standard: `false` |

### `nimlykoder.remove_code`
`slot` (int, påkrevd)

### `nimlykoder.update_name` / `update_pin` / `update_expiry`
`slot` (int, påkrevd) + respektive felt.

### `nimlykoder.list_codes` / `nimlykoder.cleanup_expired`
Ingen parametere.

---

## Node-RED

Bruk **call service**-noden fra `node-red-contrib-home-assistant-websocket`.

**Auto-lås PÅ (10 sekunder):**
```json
{
  "domain": "nimlykoder",
  "service": "set_auto_lock",
  "data": { "enabled": true, "delay_seconds": 10 }
}
```

**Auto-lås AV:**
```json
{
  "domain": "nimlykoder",
  "service": "set_auto_lock",
  "data": { "enabled": false }
}
```

**Les status** — bruk **current state**-noden på:
- `binary_sensor.nimlykoder_auto_lock_enabled` → `on`/`off`
- `sensor.nimlykoder_auto_lock_delay` → antall sekunder

> **Viktig:** Feltnavnene er `enabled` og `delay_seconds` — ikke `auto_lock_enabled`/`auto_lock_delay`.

---

## Feilsøking

**Aktivitetslogg viser ingen nye hendelser**
Lytteren registreres med forsinkelse (prøver automatisk etter 5→10→20→30→60 s). For å se INFO-logger:
```yaml
logger:
  default: warning
  logs:
    custom_components.nimlykoder: info
```

**Batterisensor mangler**
Installer quirken og rekonfigurer enheten i ZHA.

**Auto-lås fungerer ikke**
Sjekk at `binary_sensor.nimlykoder_auto_lock_enabled` er `on` og at enheten er rekonfigurert slik at hardware auto-lås (`autoRelockTime`) er deaktivert av quirken.
