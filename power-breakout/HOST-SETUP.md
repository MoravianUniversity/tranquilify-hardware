# Host setup — Waveshare ESP32-P4-WIFI6 + power breakout

Firmware / wiring notes for running the power breakout from a **Waveshare ESP32-P4-WIFI6** (and onboard C6). Soft-power is an **off-board experiment** on **J6 SPWR** (no MAX16150 on the breakout); this doc covers power, USB data, charger + fuel-gauge I2C, interrupts/monitoring, and the SPWR contract.

Datasheets: `../datasheets/BQ25895_datasheet.pdf`, `../datasheets/STC3115_datasheet.pdf`, `../datasheets/ESP32-P4-WIFI6-datasheet.pdf`. Board overview: `README.md`.

| Device | Part | I2C 7-bit addr |
|--------|------|----------------|
| Charger | BQ25895RTW | **`0x6A`** |
| Fuel gauge | STC3115AIQT | **`0x38`** (write `0x70` / read `0x71`) |

Both sit on the same 3.3 V host I2C bus (J3). Onboard ES8311 at `0x18` shares the Waveshare bus and does not collide.

---

## 1. Header wiring

Breakout connectors → Waveshare. Confirm silkscreen orientation on both boards before soldering harnesses.

### J1 POWER (JST-GH 3) → Pico power cluster (pins 36–38)

ESP32-P4-WIFI6 uses a **Raspberry Pi Pico–style** 40-pin header. J1 is ordered to plug straight across that end:

| J1 | Net | Waveshare header | Notes |
|----|-----|------------------|--------|
| 1 | `GND` | **Pin 38** `GND` | |
| 2 | `HOST_3V3_EN` | **Pin 37** `3V3_En` | OD low while breakout `SYS` is up — disables the Waveshare MP1658 so breakout `+3V3` owns `ESP_3V3` |
| 3 | `+3V3` | **Pin 36** `3V3_Out` | Switched 3.3 V into `ESP_3V3` |

**Rules**

- Power the P4/C6 from breakout `+3V3` with `HOST_3V3_EN` asserted (low), not by paralleling an active Waveshare 3V3 regulator.
- Prefer **not** powering the Waveshare from its Type-C at the same time as breakout `+3V3` (risk of dual sources on `VCC_5V` / `ESP_3V3`). UART/debug Type-C can still be used once the rail is already up from the breakout.
- Leave Waveshare **VBUS** (pin 40) / **VSYS** (pin 39) disconnected from the breakout.

### J2 USB_HDR (JST-GH 4) → USB HS data only

Prefer the Waveshare **MX1.25 4-pin USB** header (`P1`), not the 40-pin Pico header:

| J2 | Net | Waveshare MX1.25 USB (`P1`) |
|----|-----|-----------------------------|
| 1 | *(N/C)* | Leave open (do not feed `VBUS`/`VCC_5V`) |
| 2 | `HOST_DN` | Pin 1 `USBD_N` |
| 3 | `HOST_DP` | Pin 2 `USBD_P` |
| 4 | `GND` | Pin 3 `GND` |

MX1.25 pin 4 is board `VCC_5V` — **leave unconnected**. Use this path for native USB HS (download / OTG) after the breakout FSUSB42 mux hands D+/D− to the host (post BC1.2). Keep Waveshare Type-C for UART/debug when needed.

### J3 CONTROL (JST-GH 5) — charger + gauge

| J3 | Net | Suggested Waveshare (Pico header) | Host use |
|----|-----|-----------------------------------|----------|
| 1 | `GND` | Any `GND` (e.g. pin 3, 8, 13, …) | Ground |
| 2 | `SCL` | **GPIO8** — header **pin 16** | I2C clock (board default I2C) |
| 3 | `SDA` | **GPIO7** — header **pin 17** | I2C data |
| 4 | `CHG_INT` | **GPIO4** — header **pin 12** | BQ25895 `/INT` (OD; RN1 pull-up to `+3V3`) |
| 5 | `BAT_ALM` | **GPIO2** — header **pin 15** | STC3115 `ALM` (OD; RN1 pull-up to `+3V3`) |

Breakout already has 10 kΩ pull-ups on SCL/SDA (and OD interrupt nets via RN1) to `+3V3`. Waveshare also has external I2C pull-ups — disable ESP internal pull-ups (`enable_internal_pullup = false`).

`CHG_INT` / `BAT_ALM` GPIOs are suggestions (any free inputs work). Configure **falling-edge** interrupts; both lines are open-drain active-low.

**Note:** `BAT_ALM` is pulled to switched `+3V3`, so the host only sees gauge alarms while the rail is up (which is when critical-battery auto-off firmware can act). The gauge itself stays powered from the pack.

There are **no** `BTN_INT` / `PWR_CLR` pins on this breakout — soft-power host signals belong on whatever you attach to **J6** (or a later main board).

### J6 SPWR (1×4, 1.27 mm) — soft-power experiment port

| J6 | Net | Notes |
|----|-----|--------|
| 1 | `SYS` | Always-on (charger SYS). Power for an optional soft-power circuit. |
| 2 | `GND` | Ground |
| 3 | `BTN` | Active-low; also tied to BQ25895 `/QON` (ship wake). No on-board button jack — short to GND or put the switch on the daughterboard. |
| 4 | `BUCK_EN` | TPS62823 `EN` (active high). On-board **100 kΩ** pull-up to `SYS` ⇒ **default on** when the header is empty. |

**Electrical contract**

- Leave J6 open for bring-up: `+3V3` rises whenever `SYS` is present (USB and/or battery). That is intentional for lab boards; product “no auto-on on plug-in” needs a SPWR daughter.
- To soft-off: drive or OD-pull **`BUCK_EN` low** (must overcome R16; any normal OD/MCU pin is fine).
- Do not fight `/QON` on `BTN` (active-low open or switch to GND only).

**Implementation options (examples)**

| Approach | How it uses J6 | Notes |
|----------|----------------|--------|
| **MAX16150** (or similar pushbutton IC) | VCC←`SYS`, PB_IN←`BTN`, OUT→`BUCK_EN`; route INT/CLR to the host yourself | Closest to the old on-board design; hold-to-on / one-shot INT / CLR. Datasheet still under `../datasheets/MAX16150_datasheet.pdf`. |
| **Discrete latch / OD MOSFET** | Latch or FET between `SYS`/`GND`/`BTN`/`BUCK_EN` | Cheap; you own debounce and host signaling. |
| **Host GPIO daughter** | MCU always-on from `SYS` (or from `+3V3` once up) drives `BUCK_EN` | Flexible; need a policy for cold boot / first on. |
| **None** | Leave open | Default-on; use `BTN`–`GND` only to test ship `/QON`. |

Ship mode remains charger I2C (`BATFET_DIS`) regardless of which soft-power option you pick.

---

## 2. BQ25895 register init (I2C `0x6A`)

Matches schematic FW notes and ~**1 A** charge into a **4.208 V** 1S pack. Hardware `ILIM` still clamps input current. After the first I2C write the device enters host mode and the **watchdog is live** unless disabled.

### Required at boot

| Addr | Register | Action | Suggested write | Why |
|------|----------|--------|-----------------|-----|
| `0x02` | REG02 | Clear `MAXC_EN` + `HVDCP_EN` | e.g. **`0x31`** (from POR `0x3D`: keep `ICO_EN`, `BOOST_FREQ`, `AUTO_DPDM_EN`; clear bits 3–2) | MaxCharge/HVDCP hold DSEL on the charger; clearing them lets the FSUSB42 mux release D+/D− to J2 after BC1.2 |
| `0x03` | REG03 | Disable OTG; keep charge on | e.g. **`0x1A`** (`OTG_CONFIG=0`, `CHG_CONFIG=1`, `SYS_MIN=3.5 V`) | POR enables OTG (`OTG_CONFIG=1`); not used here |
| `0x04` | REG04 | Set `ICHG` | **`0x10`** → **1024 mA** | Target ~1 A; ILIM pin remains the hard max |
| `0x06` | REG06 | Charge voltage | **`0x5E`** (POR) → **VREG = 4.208 V** | Pack charge voltage; already the default — write explicitly so a watchdog expiry doesn’t surprise you later |
| `0x07` | REG07 | Disable watchdog | e.g. **`0x8D`** (from POR `0x9D`: `WATCHDOG=00`, keep `EN_TERM` / safety timer) | Otherwise host must set `WD_RST` (REG03 bit 6) every 40–160 s |

Optional:

| Addr | Register | Action | Notes |
|------|----------|--------|--------|
| `0x00` | REG00 | Raise `IINLIM` after detection if needed | POR often 500 mA until DPDM finishes; set ≥1500 mA for wall USB if detection leaves you short. Keep `EN_ILIM=1` so the ILIM pin still participates. |
| `0x02` | REG02 | Continuous ADC | Set `CONV_RATE=1` (and/or pulse `CONV_START`) when you want telemetry |
| `0x09` | REG09 | Ship mode | Set `BATFET_DIS=1` when shipping (see below) |

### DSEL / USB handoff

1. USB-C plug → charger runs BC1.2 on D+/D− (mux HSD1).
2. Host clears `MAXC_EN` + `HVDCP_EN` (and leaves `AUTO_DPDM_EN` alone unless debugging).
3. DSEL goes high → mux HSD2 → `HOST_DP`/`HOST_DN` on J2 → Waveshare USBD.

Until that handoff completes, treat native USB on the P4 as unavailable; use Waveshare Type-C UART if you need a console during bring-up.

### Ship mode

Set `BATFET_DIS=1` in **REG09**. Optional `BATFET_DLY=1` delays turn-off by `tSM_DLY`. Exit via long `/QON` (pull **J6 `BTN`** to GND, or whatever switch feeds that net) or USB plug. After exit, registers are back at POR — **re-run init**.

### Encoding quick reference

```
ICHG_mA = sum of set bits in REG04[6:0]     # 64 mA LSB; 0x10 = 1024 mA
VREG_V  = 3.840 + REG06[7:2] * 0.016       # 0b010111 = 4.208 V
IINLIM_mA = REG00[5:0] * 50                # with EN_ILIM=1, actual limit = min(IINLIM, ILIM pin)
WATCHDOG: REG07[5:4] = 00 disable; 01=40s; 10=80s; 11=160s
```

---

## 3. STC3115AIQT register init (I2C `0x38`)

Hardware: low-side **R9 = 10 mΩ**, Kelvin CG/GND, target pack **~3500 mAh**. BATD/CD and RSTIO are disabled in the schematic (detect/reset features off). Gauge VCC is on pack/`PACK+` (always on while the battery is present).

### Boot / POR recovery

1. Probe `REG_ID` (addr `24`) — expect **`0x14`**.
2. Read `REG_CTRL` (addr `1`). If `PORDET=1`, the RAM/config was reset — re-run the table below, then write `PORDET=0` to clear.
3. Apply config **before** setting `GG_RUN=1`.

### Required config

| Addr | Register | Action | Suggested value | Why |
|------|----------|--------|-----------------|-----|
| `15–16` | `REG_CC_CNF` | Coulomb-counter scale | **`707`** (LE: `0xC3`, `0x02`) | `Rsense_mΩ × Cnom_mAh / 49.556` ≈ `10 × 3500 / 49.556` |
| `17–18` | `REG_VM_CNF` | Voltage-gauge fit | leave POR **`321`** unless the pack is characterized | Default is usually fine for bring-up |
| `19` | `REG_ALARM_SOC` | Low-SOC alarm | e.g. **`0x14`** = **10%** (0.5 %/LSB) | Soft warn / critical path; tune in product FW |
| `20` | `REG_ALARM_VOLTAGE` | Low-voltage alarm | e.g. **`0xBB`** ≈ **3.30 V** (17.6 mV/LSB; POR `0xAA` ≈ 2.99 V) | Harder floor after SOC warn; tune to pack |
| `0` | `REG_MODE` | Mixed mode + run + ALM | **`0x18`** = `GG_RUN=1`, `ALM_ENA=1`, **`VMODE=0`** | POR is voltage-only standby (`VMODE=1`, `GG_RUN=0`); clear `VMODE` for OptimGauge mixed mode |

Multi-byte registers are **little-endian** (low byte at the lower address). Read/write 16-bit pairs in one I2C transaction.

### Telemetry (poll while running)

| Addr | Register | Decode |
|------|----------|--------|
| `2–3` | `REG_SOC` | SOC% = code / 512 |
| `6–7` | `REG_CURRENT` | Signed; LSB = 5.88 µV across R9 → **I_mA ≈ code × 0.588** at 10 mΩ |
| `8–9` | `REG_VOLTAGE` | Signed; **V_mV = code × 2.2** |
| `10` | `REG_TEMPERATURE` | Signed °C |
| `1` | `REG_CTRL` | `GG_VM` (CC vs VM SOC source), `BATFAIL`, `ALM_SOC` / `ALM_VOLT` latches, `PORDET` |

---

## 4. Interrupts and monitoring

### `CHG_INT` (J3 pin 4) — BQ25895

- Open-drain, ~256 µs active-low pulse on status/fault change; local pull-up to `+3V3`.
- On falling edge: read **REG0B** (status) and **REG0C** (faults). Reading REG0C clears the fault latch.

| Addr | Role |
|------|------|
| `0x0B` | Status — `VBUS_STAT`, `CHRG_STAT`, `PG_STAT`, `SDP_STAT`, `VSYS_STAT` |
| `0x0C` | Faults — watchdog, boost, charge fault, BAT OVP, NTC |

**Watch for**

- `VBUS_STAT` — adapter present / type (SDP/CDP/DCP/unknown)
- `CHRG_STAT` — not charging / precharge / fast charge / done
- `PG_STAT` — input power good
- `CHRG_FAULT` / `BAT_FAULT` / `WATCHDOG_FAULT` / `NTC_FAULT`

TS is hardware-biased for “OK” (no pack NTC). `NTC_FAULT` should stay clear in normal use; treat asserts as a bias/wiring fault.

### Charger ADC telemetry (REG02 + REG0E–REG12)

Set `CONV_RATE=1` for ~1 s continuous conversion (or `CONV_START=1` for one-shot), then read:

| Addr | Quantity | Decode |
|------|----------|--------|
| `0x0E` | `BATV` | VBAT = 2.304 V + code×20 mV |
| `0x0F` | `SYSV` | VSYS = 2.304 V + code×20 mV |
| `0x11` | `VBUSV` | VBUS = 2.6 V + code×100 mV (bit7 = VBUS attached) |
| `0x12` | `ICHGR` | charge current = code×50 mA |

Also useful: REG0E bit 7 `THERM_STAT` (thermal regulation). Prefer STC3115 for pack SOC/current once the gauge is initialized; charger ADC is still useful for VBUS / charge-current cross-checks.

### `BAT_ALM` (J3 pin 5) — STC3115

- Open-drain, driven low on low-SOC and/or low-voltage (when `ALM_ENA=1`); local pull-up to `+3V3`.
- On falling edge:
  1. Read `REG_CTRL` — check `ALM_SOC` / `ALM_VOLT`.
  2. Read `REG_SOC` / `REG_VOLTAGE` for the actual levels.
  3. Clear the latch(es) by writing **0** to `ALM_SOC` and/or `ALM_VOLT`.
  4. ALM stays low until the condition clears and the latch is cleared; the condition must go away and return before another edge for that same alarm.
- Typical product behavior: SOC alarm first (warn / reduce load); voltage alarm later → **critical auto-off** by deasserting **`BUCK_EN`** on the soft-power path (J6), once that daughter exists.

Also poll `BATFAIL` in `REG_CTRL` (battery removal / UVLO) and clear by writing 0.

### Host checklist

1. Wire J1 / J2 / J3 (`SCL`, `SDA`, `CHG_INT`, `BAT_ALM`). Leave **J6** open unless testing soft-power or `/QON`.
2. Boot with breakout USB-C or battery so `+3V3` comes up (default-on with empty SPWR); confirm I2C sees **`0x6A`** and **`0x38`** (`REG_ID=0x14`).
3. BQ25895 init: **clear MAXC/HVDCP**, **OTG off**, **ICHG=1024 mA**, **VREG=4.208 V**, **watchdog off**.
4. STC3115 init: **`CC_CNF≈707`**, alarm thresholds, **`VMODE=0` + `GG_RUN=1` + `ALM_ENA=1`**; clear `PORDET` if set.
5. Falling-edge ISRs on `CHG_INT` and `BAT_ALM`; clear charger REG0C / gauge `ALM_*` latches.
6. Poll gauge SOC/voltage/current; optionally enable charger continuous ADC for VBUS/ICHGR.
7. (Later) soft-power on **J6** (MAX16150, discrete latch, or similar) + ship-mode UX.

---

## Out of scope (for now)

- Choosing / building a specific soft-power daughter for J6 (MAX16150 vs simpler circuits — see J6 section)
- Codec / other I2C devices beyond sharing the bus with ES8311
- Pack-specific `VM_CNF` / OCV table characterization (defaults OK for first bring-up)
