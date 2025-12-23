# CatFlap: Flipper / RFCat Replay → Home Assistant Buttons (MQTT)

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-orange)
![License](https://img.shields.io/badge/license-MIT-green)

A “drop-in” **Home Assistant add-on** that turns a folder of replay files into **Home Assistant button entities**.

Drop files into a directory (and optional subfolders), and CatFlap will:

- Publish **MQTT Discovery** button entities automatically
- Subscribe for button presses (payload `PRESS`)
- **Transmit** the selected capture using an **RFCat-compatible CC1111 dongle** (e.g., Yard Stick One)

---

## ⚠️ Legal / Safety

You are responsible for complying with **all applicable laws and regulations**. RF transmission rules vary by **country, region, frequency band, power level, and licensing**. Only transmit signals you are **authorized** to transmit, and only on frequencies you are legally allowed to use.

## ✨ Features

- **MQTT Auto-Discovery:** Buttons appear automatically in Home Assistant (no YAML).
- **Folder → Device grouping:**
  - Files in the root directory become a “Misc Files” device
  - Each subfolder becomes its own device in Home Assistant
- **Icons (optional):** Set per-folder/per-file MDI icons using `.mdi-icon` and `.icon` files (with sensible defaults).
- **Supported replay formats:**
  - Flipper Zero Sub-GHz **`.sub`** files with `RAW_Data`
  - **`.rfcat.json`** for explicit RFCat/rflib settings + payload
- **Retained discovery + cleanup:** Removed files are removed from Home Assistant automatically (stale discovery topics are deleted).
- **Bridge Status entity:** Publishes a “Bridge Status” binary sensor to show when the add-on is running.


---

## How it works

1) CatFlap scans `sub_directory` for supported files (`.sub`, `.rfcat.json`).

2) For each replay file, CatFlap publishes a Home Assistant **MQTT Discovery “button”** with a `command_topic`.

3) When you press a button in Home Assistant, HA publishes `PRESS` to that topic.

4) CatFlap receives the `PRESS`, parses the file, configures RFCat modem settings, and transmits the replay via CC1111.


---

## 📦 Installation

### Option A: Home Assistant Add-on (recommended)

1) Add this repository in Home Assistant:

**Settings → Add-ons → Add-on Store → ⋮ → Repositories**

2) Install **CatFlap**, configure MQTT, and start it.

3) Put replay files here:

- `/share/tx_files`

Optional: group into folders:

- `/share/tx_files/light/`
- `/share/tx_files/garage/`
- `/share/tx_files/outlet/`

---

### Option B: Docker (advanced)

CatFlap reads `src/config.json`.

1) Copy the example config:

- `cp config.json.example src/config.json`

2) Edit `src/config.json` (MQTT + folder)

3) Run the container with USB access to your CC1111 device.

---

### Option C: Native (advanced)

```bash
python -m venv venv
. venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

## ⚙️ Configuration (Home Assistant Add-on)

In the add-on UI you’ll set:

- `mqtt_broker` (e.g. `core-mosquitto` or an IP)
- `mqtt_port` (default `1883`)
- `mqtt_user` / `mqtt_password`
- `node_id` (default `catflap`) — becomes the base MQTT topic (e.g. `catflap/...`)
- `sub_directory` (default `/share/tx_files`)
- `tx_power` (default `max`) — CC1111 transmit power for **all** replays:
  - `max` (or empty): call RFCat `setMaxPower()` before transmitting
  - `default` / `auto`: don’t change power registers (use the dongle’s current setting)
  - a number like `8` or `0x08`: call RFCat `setPower(<value>)` / `setTxPower(<value>)`
### TX power: what the number means

CatFlap supports four transmit-power modes:

- `tx_power_mode: smart` (default) — **band + target dBm → PATABLE code** using the TI reference table below
- `tx_power_mode: max` — calls rflib `setMaxPower()` (quick “just make it work” option)
- `tx_power_mode: default` — leaves the dongle’s current power configuration untouched
- `tx_power_mode: manual` — programs **FREND0** + **PATABLE** directly (advanced)

#### Smart mode (recommended)

Smart mode is the “human readable” interface:

- `tx_power_target_dbm` picks a target output level from the TI table
- `tx_power_band: auto` infers the band bucket (315/433/868/915) from the replay file’s TX frequency

Example:

    tx_power_mode: smart
    tx_power_target_dbm: 0
    tx_power_band: auto

Lookup table (hex value with decimal in parentheses):

| Target output (dBm) | 315 MHz | 433 MHz | 868 MHz | 915 MHz |
|---:|:---:|:---:|:---:|:---:|
| -30 | `0x12` (18) | `0x12` (18) | `0x03` (3) | `0x03` (3) |
| -20 | `0x0D` (13) | `0x0E` (14) | `0x0E` (14) | `0x0D` (13) |
| -15 | `0x1C` (28) | `0x1D` (29) | `0x1E` (30) | `0x1D` (29) |
| -10 | `0x34` (52) | `0x34` (52) | `0x27` (39) | `0x26` (38) |
|  -5 | `0x2B` (43) | `0x2C` (44) | `0x8F` (143) | `0x57` (87) |
|   0 | `0x51` (81) | `0x60` (96) | `0x50` (80) | `0x8E` (142) |
|   5 | `0x85` (133) | `0x84` (132) | `0x84` (132) | `0x83` (131) |
|   7 | `0xCB` (203) | `0xC8` (200) | `0xCB` (203) | `0xC7` (199) |
|  10 | `0xC2` (194) | `0xC0` (192) | `0xC2` (194) | `0xC0` (192) |

Notes:

- Output power is **approximate**: real dBm depends on band, matching network, antenna, board layout, and supply voltage.
- Some PA settings are discouraged/invalid on certain boards; treat the table as **starting points**, not a calibrated RF power meter.

#### Manual mode (FREND0 + PATABLE)

Manual mode exposes the CC111x fields that drive TX output:

- `frend0_pa_power` (0–7): sets **FREND0.PA_POWER[2:0]** (selects the PATABLE index used for TX power)
- `frend0_lodiv_buf_current_tx` (0–3): sets **FREND0.LODIV_BUF_CURRENT_TX[1:0]** (TX LO buffer current)
- `patable`: sets **PA_TABLE0..7** (PA shaping/ramp and output level codes)

How CatFlap treats `patable`:

- A single value like `"0xC0"` is treated as a convenience “ON level”
  - For **ASK/OOK**, CatFlap forces `PA_TABLE0 = 0x00` and fills indices `1..PA_POWER` with the ON value
  - For **FSK/GFSK/MSK**, CatFlap fills indices `0..PA_POWER` with the ON value
- A comma list (up to 8 values) defines an explicit shaping/ramp table



For further information, please refer to cc1110-cc1111 data sheet
- https://www.ti.com/lit/ds/symlink/cc1110-cc1111.pdf



## ▶️ Usage

Once running, buttons will appear in Home Assistant under MQTT devices.

Expected log snippets:

```text
[MQTT] Connecting to core-mosquitto:1883 ...
[MQTT] Connected
[Files] Mapped 12 replay topics
[MQTT] Trigger: catflap/door/front_door/set
[RfCat] Replaying front_door.sub
[RfCat] Transmission complete
```

---

## 🎨 Icons (optional)

CatFlap can assign **Material Design Icons (MDI)** to the entities it creates via MQTT Discovery.

Icon resolution order (highest priority first):

1) **Per-file override**: a sidecar icon file next to the replay file  
2) **Per-folder default**: a `.mdi-icon` file in the folder (inherited by subfolders)  
3) **Name-based defaults**: common keywords like `door`, `garage`, `gate`, `light`, etc.  
4) **Fallback**: `mdi:radio-tower`

### Per-folder icons: `.mdi-icon` (inherits)

Create a file named `.mdi-icon` inside `/share/tx_files/` or any subfolder. The **first line** is the icon:

- Either `mdi:garage` **or** just `garage` (it will be normalized to `mdi:garage`)

The nearest `.mdi-icon` wins, so subfolders inherit the closest parent.

Example:

```text
/share/tx_files/.mdi-icon
/share/tx_files/garage/.mdi-icon
```

```text
# /share/tx_files/.mdi-icon
mdi:radio-tower

# /share/tx_files/garage/.mdi-icon
mdi:garage
```

### Per-file icons: `<name>.icon`

To override one button, create a sidecar file next to the replay file:

- `front_door.icon` (preferred)  
- or `front_door.sub.icon`

Example:

```text
/share/tx_files/doors/front_door.sub
/share/tx_files/doors/front_door.icon
```

```text
# /share/tx_files/doors/front_door.icon
mdi:door
```

### Gateway icon (Bridge Status)

The gateway’s **Bridge Status** entity uses `device_info.default_entity_icon` as its default (fallback: `mdi:radio-tower`).

If you want the gateway to be a **cat** while keeping most buttons as **radio-tower**, set:

- `device_info.default_entity_icon` = `mdi:cat`
- and create `/share/tx_files/.mdi-icon` with `mdi:radio-tower`

Example config snippet:

```json
{
  "device_info": {
    "default_entity_icon": "mdi:cat"
  }
}
```

---

## 📁 Supported file formats

### 1) Flipper Zero `.sub` (RAW)

CatFlap supports `.sub` files **only when they include `Frequency:` and `RAW_Data:`**.

Minimal example:

```text
Filetype: Flipper SubGhz Key File
Version: 1
Frequency: 433920000
Protocol: RAW
RAW_Data: 350 -700 350 -700 350 -700
```

---

### 2) `.rfcat.json`

Use this when you want explicit RFCat/rflib settings.

Example:

```json
{
  "frequency": 433920000,
  "modulation": "ASK_OOK",
  "repeat": 5,
  "drate": 4800,
  "payload_hex": "deadbeef"
}
```

Supported payload inputs (choose one):

- `payload_hex`
- `payload_b64`
- `payload` (list of ints 0–255)
- `raw_durations_us` (list of pulse durations; positive = high, negative = low)

Optional RF settings:

- `modulation` (`ASK_OOK`, `2FSK`, `GFSK`, `MSK`)
- `repeat`, `drate`, `deviation`, `syncmode`, `preamble`, `manchester`, `max_power`
- `invert_level`, `msb_first`, `max_gap_us` (for raw duration conversion)

---

## 🧰 Troubleshooting

**No buttons appear**
- Confirm the MQTT integration works and you have a broker configured
- Check add-on logs
- Verify the files exist under `/share/tx_files` (and have the supported extensions)

**“No Dongle Found” / transmit fails**
- Confirm the CC1111 dongle is connected and supported by RFCat/rflib
- Restart the add-on after plugging in the dongle
- If you’re running outside HA, make sure the container has USB access

**Entities won’t disappear after deleting files**
- CatFlap uses retained MQTT discovery and cleans up stale topics automatically
- If you want a clean slate, delete the cache file (if used) and restart:
  - `/share/.discovery_cache.json`

---
