# Power Breakout

Battery + USB-C power path breakout for Tranquilify. Supplies switched **+3.3 V** to an ESP32-P4 (and onboard C6), two ADAU1787 codec boards, with charge-while-off, ship mode, and I2C fuel gauging.

Schematic-first; PCB later. Target assembly: JLCPCB.

## Role in the system

| Consumer | Rail | Notes |
|----------|------|--------|
| ESP32-P4 + ESP32-C6 | `+3V3` (switched) | Soft power via buck EN / host `HOST_3V3_EN` |
| 2× ADAU1787 breakouts | `+3V3` | Codecs make their own 1.8 V on-board |
| STC3115 fuel gauge | Battery (always) | Low-side sense; I2C @ 0x38 on host bus |
| Soft-power + charger | Always-on from `SYS` / pack | Charge LED works while “off”; soft-power is off-board via J6 |

## Locked requirements

- **USB-C** 5 V sink only; **USB HS** D+/D− shared with charger BC1.2 via DSEL mux
- **Power path:** system runs from USB with empty or **missing** battery
- **Battery:** ~3500 mAh 1S Li-ion target (was Adafruit 353 6600 mAh), JST-PH, pack PCM, **no NTC**
- Charge ~**1 A** (pack max 1.5 A; ICHG in firmware + ILIM pin)
- Soft power = **Mode B** (cut system load / Waveshare 3V3_EN); path toward deep-sleep later
- Soft-power UX (hold-to-on, no auto-on on plug-in, click/hold to host) is **off-board** on **J6 SPWR** — not populated on this rev
- Critical-battery auto-off via gauge + firmware (once soft-power can cut `BUCK_EN`)
- Ship mode via BQ25895 `BATFET_DIS` / `/QON` wake
- Connectors: JST-PH battery; JST-GH for power, control, USB data; 1.27 mm header for soft-power experiments

## Architecture

```
USB-C VBUS ──► BQ25895 (power path, ~1 A charge)
                 │
    D+/D− ──► FSUSB42 (DSEL) ──┬── CHG_DP/DN → BQ25895 BC1.2
                               └── HOST_DP/DN → J2 USB header
                 │
    PACK+ ◄──────┤◄── JST-PH pin1; charger BAT = PACK+
                 │
                SYS
                 │
   ┌─────────────┼──────────────────┐
   │             │                  │
always-on   R16 100k ↑ EN      STAT → CHG LED
(SYS)            │
                 ▼
         TPS62823 EN → +3V3 → P4 / C6 / codecs
                 │
         J1 POWER: GND / HOST_3V3_EN (OD) / +3V3

    PACK- (JST-PH pin2) ── 10 mΩ R9 ──► GND   (STC3115 CG/GND Kelvin)

J6 SPWR: SYS / GND / BTN / BUCK_EN
  BTN also → BQ25895 /QON (ship wake)
  Empty header ⇒ EN pulled up ⇒ +3V3 default on when SYS is up
STC3115 low-side sense on PACK-, I2C @ 0x38 (host bus, not codec bus)
```

RGB indicator lives on the eventual main board, not this power breakout.

**Dropped vs earlier draft:** no LM66200 / `AUX_5V` input OR. USB-C is the only VBUS source into the charger. On-board **MAX16150** soft-power IC removed in favor of **J6 SPWR** (see below).

### Soft power vs ship mode

| State | What happens |
|-------|----------------|
| **Default (no SPWR board)** | `BUCK_EN` pulled to `SYS` via R16 → `+3V3` on whenever `SYS` exists (USB and/or battery). |
| **User off (with SPWR daughter)** | Daughter deasserts `BUCK_EN` → `+3V3` down. Charger + gauge live. USB can still charge. |
| **Ship** | Host I2C → BQ25895 `BATFET_DIS`; BATFET off; ~µA. Exit: long `/QON` (BTN to GND) or USB plug. |
| **Deep sleep (later)** | Keep `+3V3` up; P4 sleep — optional future |

### Soft-power experiment port (J6 SPWR)

No on-board pushbutton controller. **J6** (1×4, 1.27 mm) exposes the always-on domain so you can try options without a power-board respin:

| Pin | Net | Contract |
|-----|-----|----------|
| 1 | `SYS` | Always-on supply for a soft-power circuit |
| 2 | `GND` | Ground |
| 3 | `BTN` | Active-low button node; also tied to BQ25895 `/QON` |
| 4 | `BUCK_EN` | TPS62823 `EN` (active high). Weak **100 kΩ** pull-up to `SYS` (R16) for default-on |

**Suggested implementations on J6**

- **MAX16150** (or similar): VCC=`SYS`, PB_IN=`BTN`, OUT→`BUCK_EN`, CLR/INT to the host as needed (host wires are no longer on J3).
- **Simpler:** discrete latch / open-drain MOSFET from a GPIO daughterboard; OD **low** on `BUCK_EN` for off.
- **Bring-up:** leave J6 open — rail stays on; short `BTN`–`GND` only if testing `/QON` / ship wake.

Product UX (hold-to-on, no auto-on on plug-in, click vs hold) lives entirely on whatever you plug into SPWR (+ host wiring you add).

### Dev board (Waveshare ESP32-P4-WIFI6)

| Mode | Intent |
|------|--------|
| **B – Rail / 3V3_EN** | Feed Waveshare from `+3V3`; `HOST_3V3_EN` OD-low while breakout `SYS` is present (disables module regulator when breakout is powering the rail). |
| USB data | Host USB via J2 (`HOST_DP`/`HOST_DN`); pin 1 V left N/C. DSEL mux hands D+/D− to host after BC1.2. |

## Major parts (schematic)

| Ref | Part | Why |
|-----|------|-----|
| U1 | **BQ25895RTW** | Switch-mode power-path charger, ship (`BATFET_DIS`), `/QON` wake, `STAT` LED, DSEL, I2C; ICHG ~1 A in firmware |
| U3 | **STC3115AIQT** | OptimGauge mixed mode; ~3500 mAh; low-side 10 mΩ; LCSC C2688637. `ALM`→`BAT_ALM` (RN1 pull-up); `RSTIO`→GND (feature off); `BATD` 1 kΩ→GND; VIN filter R11+C16; VCC C10 1 µF |
| U4 | **TPS62823DLC** | 3 A buck, VIN down to 2.4 V → `+3V3`; `EN` default-on via R16 |
| U5 | **USBLC6-2SC6** | USB ESD on `USB_DP`/`USB_DN` |
| U6 | **FSUSB42MUX** | DSEL mux: BC1.2 (HSD1) vs host USB (HSD2); OE# grounded; VCC from `SYS` |
| R16 | **100 kΩ** | `SYS` → `BUCK_EN` pull-up (default on) |
| D1 | LED + R from `STAT` | Charge LED while system off |
| J1 | JST-GH 3 POWER | `GND` / `HOST_3V3_EN` / `+3V3` |
| J2 | JST-GH 4 USB_HDR | USB data header: V N/C, D−, D+, GND |
| J3 | JST-GH 5 CONTROL | I2C + `CHG_INT` + `BAT_ALM` |
| J4 | USB-C + 5.1 kΩ CC | 5 V sink; D+/D− to ESD + mux |
| J5 | JST-PH 2-pin BAT | Battery (`PACK+` / `PACK-`) |
| J6 | 1×4 1.27 mm SPWR | Soft-power experiment: `SYS` / `GND` / `BTN` / `BUCK_EN` |

**FW notes:** clear `MAXC_EN` + `HVDCP_EN` so DSEL releases after BC1.2; set ICHG/VREG; disable or pet charger WDT.

## Datasheets

Saved under `../datasheets/`:

| File | Part |
|------|------|
| `BQ25895_datasheet.pdf` | Charger |
| `BQ25628_datasheet.pdf` | Alternate charger (no D+/D−; not used) |
| `MAX16150_datasheet.pdf` | Soft-power pushbutton IC (optional on J6; not on board) |
| `STC3115_datasheet.pdf` | Fuel gauge (STC3115AIQT) |
| `AN4324_STC3115_system_integration.pdf` | STC3115 integration (if present) |
| `TPS62823_datasheet.pdf` | 3.3 V buck |
| `LM66200_datasheet.pdf` | Dual ideal diode (not used on this rev) |
| `LM66100_datasheet.pdf` | Prior single ideal diode (not used) |
| `ESP32-P4-WIFI6-datasheet.pdf` | Waveshare host module |

## Host connectors

### J1 POWER (JST GH-3)

| Pin | Net | Notes |
|-----|-----|--------|
| 1 | `GND` | |
| 2 | `HOST_3V3_EN` | OD low while `SYS` present; floats when breakout unpowered |
| 3 | `+3V3` | Switched 3.3 V out |

### J2 USB_HDR (JST GH-4)

| Pin | Net | Notes |
|-----|-----|--------|
| 1 | — | V left N/C (host supplies USB VBUS separately if needed) |
| 2 | `HOST_DN` | From mux HSD2 |
| 3 | `HOST_DP` | |
| 4 | `GND` | |

### J3 CONTROL (JST GH-5)

| Pin | Net | Notes |
|-----|-----|--------|
| 1 | `GND` | |
| 2 | `SCL` | 3.3 V I2C (charger `0x6A`; gauge **0x38**) |
| 3 | `SDA` | |
| 4 | `CHG_INT` | BQ25895 `/INT` (OD; RN1 10 kΩ to `+3V3`) |
| 5 | `BAT_ALM` | STC3115 `ALM` (OD; RN1 10 kΩ to `+3V3`) |

### J6 SPWR (1×4, 1.27 mm)

| Pin | Net | Notes |
|-----|-----|--------|
| 1 | `SYS` | Always-on |
| 2 | `GND` | |
| 3 | `BTN` | Shared with `/QON` |
| 4 | `BUCK_EN` | Active-high enable; pulled up on board |

Also: `J4` USB-C, `J5` battery (PH, pin1=`PACK+`, pin2=`PACK-` via R9 to GND).

Host wiring detail: `HOST-SETUP.md`.

## Non-goals (this board)

- Codec 1.8 V generation (on ADAU1787 breakouts)
- RGB LED (on eventual main board)
- On-board soft-power IC / dedicated button jack (use J6)
- Battery NTC (pack has none; TS biased for “OK”)
- AUX 5 V input / ideal-diode OR (dropped this rev)
