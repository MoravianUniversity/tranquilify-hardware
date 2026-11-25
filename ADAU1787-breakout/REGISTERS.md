# ADAU1787 Boot Register Map (I2C)

Firmware guide for bringing up each `ADAU1787-breakout` board over I2C after power-on.
Values match this board’s wiring (Rev schematic / README) and Analog Devices ADAU1787 Rev. A.

Sources: `../datasheets/ADAU1787_datasheet_RevA.pdf`, board schematic / README.

---

## System assumptions (this product)

| Item | Choice | Why |
|------|--------|-----|
| Host | ESP32-P4 (or equiv.), **1.8 V logic** on J1 | Codec IOVDD is 1.8 V; not 3.3 V tolerant |
| Board supply | +3.3 V on J1 → on-board LDO → +1.8 V AVDD/HPVDD/IOVDD/`REG_EN` | Internal DVDD LDO used (`REG_EN` = +1V8) |
| Crystal | On-board **24.576 MHz** (Y1); no external MCLK | Each ear has its own crystal |
| Clock domain | **ASRC** between serial port and ADC/DAC | Host BCLK/FSYNC are not locked to either codec crystal; two codecs share one I2S bus with no shared MCLK |
| Serial port | **SPT0** only (J1: BCLK_0 / FSYNC_0 / SDATAI_0 / SDATAO_0) | SPT1 and all DMIC pins are unconnected |
| Format | **TDM**, slave, **48 kHz**, **16-bit** slots | Two codecs on one bus; each uses one TX and one RX slot |
| Capture | **FF mic → AIN0 → ADC0** (J5 / MICBIAS1) | Mono feedforward into host |
| Playback | Host → **DAC0 → HPOUT0** differential (J3 speaker) | Mono to in-ear driver |
| FB mic | AIN2 / MICBIAS0 on J3 | Available for on-chip ANC later; **not** in this I2S boot path |
| I2C address | Right **0x28**, Left **0x2A** (7-bit) | ADDR1/ADDR0 straps (see README) |
| Self-boot | Off (`SELFBOOT` hard-wired low) | Host programs registers every boot |

I2C protocol: 16-bit register address, then data (see datasheet control-port section). Verify `VENDOR_ID`/`DEVICE_ID` (`0xC000`–`0xC002` → `0x41`, `0x17`, `0x87`) before configuring.

---

## Recommended TDM slot map

Host is I2S/TDM **master**. Both codecs are **slaves** on the same BCLK / FSYNC / SDATAI / SDATAO.

| Direction | Slot 0 | Slot 1 | Slots 2+ |
|-----------|--------|--------|----------|
| Host → codecs (`SDATAI_0`) | Right speaker (DAC) | Left speaker (DAC) | unused |
| Codecs → host (`SDATAO_0`) | Right FF mic (ADC) | Left FF mic (ADC) | unused (tristate) |

Suggested host clocks for **TDM-4 × 16-bit @ 48 kHz**:

- `FSYNC` = 48 kHz, 1-BCLK-wide pulse (TDM framing)
- `BCLK` = 48 kHz × 4 × 16 = **3.072 MHz**

Enable `SPT0_TRI_STATE` so each codec only drives its own TX slot.

Per-ear differences are only: I2C address, which TDM slot is used for ASRCI / SPT0 output route. Everything else is identical.

---

## Signal path (per ear, after boot)

```
Host SDATAI slot N ──► SPT0 ──► ASRCI0 ──► DAC0 ──► HPOUTP0/HPOUTN0 ──► speaker (J3)

FF mic (J5) ──► AIN0 ──► PGA0 ──► ADC0 ──► ASRCO0 ──► SPT0 slot N ──► SDATAO ──► host
```

`N` = 0 (right) or 1 (left).

---

## Power-up sequence (order matters)

Follow datasheet power-up (Rev. A § Power-Down Operation / Example ADC→DAC), adapted for crystal + ASRC + TDM.

### Hardware before I2C

1. Apply +3.3 V on J1; wait for +1.8 V LDO settle.
2. Hold `PD_N` high (R6 pulls up; host may drive high).
3. **Wait ≥ 20 ms** after `REG_EN` is high (internal DVDD LDO).

### Software sequence

| Step | Action | Reg | Value | Notes |
|------|--------|-----|-------|-------|
| 1 | Enable digital power domains | `CHIP_PWR` `0xC00D` | `0x11` | `POWER_EN=1`, `DLDO_CTRL=01` (0.9 V). Keep `CM_STARTUP_OVER=0`, `MASTER_BLOCK_EN=0` |
| 2 | Wait **≥ 35 ms** | — | — | CM fast-charge |
| 3 | While waiting / after, program all config below **except** final `MASTER_BLOCK_EN` | — | — | PLL may still be locking |
| 4 | End CM boost | `CHIP_PWR` `0xC00D` | `0x15` | `CM_STARTUP_OVER=1` + `POWER_EN` |
| 5 | Enable crystal + PLL (after PLL regs + `PLL_UPDATE`) | `PLL_MB_PGA_PWR` `0xC005` | see below | `XTAL_EN` / `PLL_EN` |
| 6 | Poll until ready | `STATUS2` `0xC0AB` | read | Wait for `PLL_LOCK` (bit 0) and `POWER_UP_COMPLETE` (bit 7) |
| 7 | (Optional) Init DSP RAMs if using SigmaDSP/FastDSP | — | — | Not required for this ADC↔ASRC↔SAI path |
| 8 | Enable blocks | `CHIP_PWR` `0xC00D` | `0x17` | `MASTER_BLOCK_EN=1` |
| 9 | Unmute DAC0 last | `DAC_CTRL2` `0xC03B` | `0x84` | Avoid pops |

Power-down: mute DAC → clear `MASTER_BLOCK_EN` → clear `POWER_EN` (or drive `PD_N` low for full reset).

---

## Register writes

Values are the recommended boot image. Bit fields document **why** each choice was made.

### 1. Chip / clock / PLL

#### `0xC00D` — `CHIP_PWR`

| Stage | Value | Bits |
|-------|-------|------|
| First write | `0x11` | `DLDO_CTRL=01`, `POWER_EN=1` |
| After 35 ms | `0x15` | + `CM_STARTUP_OVER=1` |
| After lock + config | `0x17` | + `MASTER_BLOCK_EN=1` |

| Field | Setting | Rationale |
|-------|---------|-----------|
| `POWER_EN` | 1 | Ungates digital domains; required first |
| `CM_STARTUP_OVER` | 0→1 | Datasheet CM sequencing (`REG_EN=1`, keep-alive default) |
| `MASTER_BLOCK_EN` | 0 until end | Configure routes/enables first; then gate everything on |
| `DLDO_CTRL` | `01` (0.9 V) | Default / recommended internal DVDD |

#### `0xC00E` — `CLK_CTRL1` → `0x88`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `PLL_SOURCE` | `000` (MCLKIN/crystal) | On-board Y1 into XTALI |
| `XTAL_MODE` | 1 | Crystal oscillator (not external CMOS MCLK) |
| `PLL_TYPE` | 0 (integer) | 24.576 MHz × 2 = 49.152 MHz exactly |
| `PLL_BYPASS` | 0 | Run PLL → 49.152 MHz core (full DSP headroom later) |
| `SYNC_SOURCE` | `10` (input ASRC) | Serial clocks are async to the crystal; datasheet requires ASRC sync when SAI ≠ core clock. Shared `FSYNC_0` alone is wrong here because each chip’s PLL is free-running |

Reset default `0xC8` already has crystal + integer PLL source; only `SYNC_SOURCE` changes (`11` → `10`).

#### `0xC00F`–`0xC015` — PLL dividers (24.576 MHz → 49.152 MHz)

| Reg | Name | Value | Rationale |
|-----|------|-------|-----------|
| `0xC00F` | `CLK_CTRL2` | `0x00` | `PLL_INPUT_PRESCALER=0` (÷1); Table 13 |
| `0xC010` | `CLK_CTRL3` | `0x00` | `PLL_INTEGER_DIVIDER[12:8]=0` |
| `0xC011` | `CLK_CTRL4` | `0x02` | `R=2` (matches reset; keep explicit) |
| `0xC012`–`0xC015` | num/den | `0x00` | Ignored in integer mode |

#### `0xC016` — `CLK_CTRL9` → `0x01`

Write `PLL_UPDATE=1` after programming `0xC00E`–`0xC015`, then enable `PLL_EN`.

#### `0xC005` — `PLL_MB_PGA_PWR` → `0x1F`

(Program dividers + `PLL_UPDATE` with `PLL_EN=0` first if reconfiguring; cold boot can set this after update.)

| Field | Setting | Rationale |
|-------|---------|-----------|
| `PLL_EN` | 1 | Enable PLL after `PLL_UPDATE` |
| `XTAL_EN` | 1 | Board has crystal only |
| `MBIAS0_EN` | 1 | Bias for FB mic on J3 (keep alive even if ADC2 off) |
| `MBIAS1_EN` | 1 | Bias for FF mic on J5 |
| `PGA0_EN` | 1 | AIN0 = electret/MEMS mic path (not line-in) |
| `PGA1_EN` | 0 | AIN1 unused (J6 optional) |
| `PGA2_EN` | 0 | FB mic unused in this I2S boot image (set 1 when enabling ADC2 for ANC) |
| `PGA3_EN` | 0 | AIN3 unused |

#### `0xC02A` — `MBIAS_CTRL` → `0x00`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `MBIAS0_LEVEL` / `MBIAS1_LEVEL` | 0 → **0.9 × AVDD ≈ 1.63 V** | CMM-2718AB VDD range 1.5–3.6 V (specs at 1.8 V). 0.65×AVDD ≈ 1.17 V is below min |
| `MBIAS_IBIAS` | `00` (normal) | Default performance |

---

### 2. Unused digital pins — weak pull-downs

Schematic leaves these **NC**. Enable internal weak **pull-down** (`PULL_EN=1`, `PULL_SEL=0`). Drive/slew left at reset (4 mA, slow slew → base `0x05` + pull = `0x15`).

| Reg | Pin | Value | Notes |
|-----|-----|-------|-------|
| `0xC098` | FSYNC_1 / MP3 | `0x15` | NC |
| `0xC099` | BCLK_1 / MP4 | `0x15` | NC |
| `0xC09A` | SDATAO_1 / MP5 | `0x15` | NC |
| `0xC09B` | SDATAI_1 / MP6 | `0x15` | NC |
| `0xC09C` | DMIC_CLK0 / MP7 | `0x15` | NC |
| `0xC09D` | DMIC_CLK1 / MP8 | `0x15` | NC |
| `0xC09E` | DMIC01 / MP9 | `0x15` | NC |
| `0xC09F` | DMIC23 / MP10 | `0x15` | NC |

**Do not** enable pulls on active host pins (`FSYNC_0`, `BCLK_0`, `SDATAI_0`) while the host drives them. `SDATAO_0` (`0xC096`) has no pull bits; leave reset (`0x04`) or raise drive if SI requires it.

Leave `DMIC_PWR` / DMIC clocks powered off (`0xC006`/`0xC007` DMIC bits = 0).

---

### 3. Serial port 0 — TDM slave, 16-bit, tristate

#### `0xC0B5` — `SPT0_CTRL1` → `0x51`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `SPT0_SAI_MODE` | 1 | **TDM** (1-BCLK FSYNC pulse), not stereo I2S |
| `SPT0_DATA_FORMAT` | `000` | 1-BCLK delay (I2S-style MSB placement; also Table 38 TDM row) |
| `SPT0_SLOT_WIDTH` | `01` | **16 BCLKs/slot** (true 16-bit slots) |
| `SPT0_TRI_STATE` | 1 | Required so both codecs can share `SDATAO` |

Bit packing: `TRI_STATE | SLOT_WIDTH | DATA_FORMAT | SAI_MODE` → `0b01010001` = `0x51`.

#### `0xC0B6` — `SPT0_CTRL2` → `0x00`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `SPT0_BCLK_SRC` | `000` | Slave: host drives BCLK |
| `SPT0_LRCLK_SRC` | `000` | Slave: host drives FSYNC |
| `SPT0_BCLK_POL` / `SPT0_LRCLK_POL` | 0 | Normal edges (match ESP-IDF I2S defaults; invert only if SI fails) |

#### `0xC007` — `SAI_CLK_PWR` → `0x03`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `SPT0_IN_EN` | 1 | Playback data from host |
| `SPT0_OUT_EN` | 1 | Mic data to host |
| SPT1 / DMIC / PDM | 0 | Unused |

#### SPT0 output slot routes

Route code `0x20` = Output ASRC Channel 0. Unused slots `0x3F` = no output (tristate when `TRI_STATE=1`).

| Reg                    | Slot | Right (`0x28`)  | Left (`0x2A`)   |
| ---------------------- | ---- | --------------- | --------------- |
| `0xC0B7` `SPT0_ROUTE0` | 0    | `0x20` (ASRCO0) | `0x3F`          |
| `0xC0B8` `SPT0_ROUTE1` | 1    | `0x3F`          | `0x20` (ASRCO0) |
| `0xC0B9`–`0xC0C6`      | 2–15 | `0x3F`          | `0x3F`          |

---

### 4. ASRC (mandatory for this clocking)

#### `0xC059` — `ASRCI_CTRL` → `0x02`

Input ASRC: serial port → internal 48 kHz for DAC.

| Field | Setting | Rationale |
|-------|---------|-----------|
| `ASRCI_SOURCE` | 0 | From **SPT0** |
| `ASRCI_OUT_FS` | `010` (48 kHz) | Match DAC / system rate |
| `ASRCI_LPM` / `LPM_II` / voice filters | 0 | Full performance for prototype |

#### `0xC05A` — `ASRCI_ROUTE01`

| Ear   | Value  | Meaning                            |
| ----- | ------ | ---------------------------------- |
| Right | `0x00` | `ASRCI0_ROUTE` = serial slot **0** |
| Left  | `0x01` | `ASRCI0_ROUTE` = serial slot **1** |

(`ASRCI1` unused; leave nibble 0.)

#### `0xC05C` — `ASRCO_CTRL` → `0x02`

Output ASRC: internal ADC → serial port rate.

| Field | Setting | Rationale |
|-------|---------|-----------|
| `ASRCO_SAI_SEL` | 0 | Rate reference = **SPT0** |
| `ASRCO_IN_FS` | `010` (48 kHz) | Match ADC0 rate |
| LPM / filters | 0 | Full performance |

#### `0xC05D` — `ASRCO_ROUTE0` → `0x20`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `ASRCO0_ROUTE` | `100000` = ADC0 | FF mic path into ASRC → TDM |

#### `0xC009` — `ASRC_PWR` → `0x11`

Enable `ASRCI0_EN` and `ASRCO0_EN` only.

---

### 5. ADC0 (FF mic) + DAC0 / HP0 (speaker)

#### `0xC004` — `ADC_DAC_HP_PWR` → `0x11`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `ADC0_EN` | 1 | FF mic |
| `PB0_EN` | 1 | DAC0 + HPOUT0 |
| `ADC1/2/3`, `PB1` | 0 | Unused / deferred (FB mic = ADC2 later) |

#### `0xC017` — `ADC_CTRL1` → `0x22` (reset OK)

Both ADC pairs at **48 kHz** (`ADC01_FS` / `ADC23_FS` = `010`). Keep for consistency.

#### `0xC019` — `ADC_CTRL3` → `0x01`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `ADC0_HPF_EN` | 1 | Remove residual DC after AC-coupling |

#### `0xC01C` — `ADC_MUTES` → `0x00`

ADC0 unmuted (default).

#### `0xC01D` — `ADC0_VOL` → `0x40`

0 dB digital (default). Tune later.

#### `0xC021` / `0xC022` — PGA0 → `0x00` **/** `0x00`

Start at **0 dB**, no 10 dB boost, slew enabled. CMM-2718AB is ≈ −38 dBV @ 1 Pa; raise `PGA0_GAIN` / `PGA0_BOOST` after measuring levels.

#### `0xC03A` — `DAC_CTRL1` → `0x02`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `DAC_FS` | `010` (48 kHz) | Match ASRC / host |
| `DAC_LPM` | 0 | Full performance; set 1 later to save power |

#### `0xC03E` — `DAC_ROUTE0` → `0x40`

| Setting | Meaning |
|---------|---------|
| `1000000` | **Input ASRC Channel 0** → DAC0 (playback through ASRC) |

Do **not** use the datasheet’s ADC0→DAC0 example (`0x44`) for this I2S path.

#### `0xC040` — `HP_CTRL` → `0x01`

| Field | Setting | Rationale |
|-------|---------|-----------|
| `HP0_MODE` | 1 | **Headphone** mode for HPOUTP0/HPOUTN0 (speaker / receiver load) |
| `HP1_MODE` | 0 | HPOUT1 unconnected |

#### `0xC03C` — `DAC_VOL0` → `0x40`

0 dB start; attenuate if the driver is too loud.

#### `0xC03B` — `DAC_CTRL2` → `0x84` (after `MASTER_BLOCK_EN`)

| Field | Setting | Rationale |
|-------|---------|-----------|
| `DAC0_MUTE` | 0 | Unmute speaker path |
| `DAC1_MUTE` | 1 | Keep unused DAC1 muted |
| `DAC_VOL_ZC` | 1 | Soft volume changes at zero-cross (reset default) |

---

### 6. Blocks left off

| Block | Reg | Value | Why |
|-------|-----|-------|-----|
| DMIC | `0xC006` | `0x00` | No digital mics |
| DSP | `0xC008` | `0x00` | No SigmaDSP/FastDSP program yet |
| FINT / FDEC | `0xC00A` / `0xC00B` | `0x00` | Not in this path |
| SPT1 | `0xC0C7`+ | leave reset | Port unconnected |
| ADC2 (FB) | — | off | Enable later for on-chip ANC with `PGA2_EN` + `ADC2_EN` |

---

## Ordered write list (copy-paste checklist)

Addresses are hex. Do right (`0x28`) and left (`0x2A`) with the noted slot differences.

```
# --- Power ---
W 0xC00D  0x11          # POWER_EN; wait >= 35 ms from this point for CM
# (optional: start programming the following during the wait)

# --- Unused pin pull-downs ---
W 0xC098  0x15          # FSYNC_1 PD
W 0xC099  0x15          # BCLK_1 PD
W 0xC09A  0x15          # SDATAO_1 PD
W 0xC09B  0x15          # SDATAI_1 PD
W 0xC09C  0x15          # DMIC_CLK0 PD
W 0xC09D  0x15          # DMIC_CLK1 PD
W 0xC09E  0x15          # DMIC01 PD
W 0xC09F  0x15          # DMIC23 PD

# --- Clock / PLL (crystal 24.576 MHz -> 49.152 MHz) ---
W 0xC00E  0x88          # XTAL mode, integer PLL, SYNC=ASRC
W 0xC00F  0x00          # prescaler /1
W 0xC010  0x00
W 0xC011  0x02          # R=2
W 0xC012  0x00
W 0xC013  0x00
W 0xC014  0x00
W 0xC015  0x00
W 0xC016  0x01          # PLL_UPDATE
W 0xC005  0x1F          # PLL+XTAL+MBIAS0/1+PGA0

# --- After CM wait ---
W 0xC00D  0x15          # CM_STARTUP_OVER=1

# --- Mic bias level ---
W 0xC02A  0x00          # 0.9*AVDD on both biases

# --- SAI / TDM ---
W 0xC0B5  0x51          # TDM, 16-bit slots, I2S delay, tristate
W 0xC0B6  0x00          # slave BCLK/FSYNC
W 0xC007  0x03          # SPT0 in+out

# Right ear TX/RX slot 0; Left ear slot 1:
#   Right:  W 0xC0B7 0x20 ; W 0xC0B8 0x3F ; W 0xC05A 0x00
#   Left:   W 0xC0B7 0x3F ; W 0xC0B8 0x20 ; W 0xC05A 0x01
W 0xC0B9..0xC0C6  0x3F  # all other TX slots off

# --- ASRC ---
W 0xC059  0x02          # ASRCI from SPT0 @ 48 kHz
W 0xC05C  0x02          # ASRCO to SPT0 rate, in FS 48 kHz
W 0xC05D  0x20          # ASRCO0 <- ADC0
W 0xC009  0x11          # ASRCI0 + ASRCO0 on

# --- ADC / DAC / HP ---
W 0xC004  0x11          # ADC0 + PB0
W 0xC017  0x22          # ADC FS 48 kHz
W 0xC019  0x01          # ADC0 HPF
W 0xC01C  0x00          # ADC unmute
W 0xC01D  0x40          # ADC0 vol 0 dB
W 0xC021  0x00          # PGA0 0 dB
W 0xC022  0x00
W 0xC03A  0x02          # DAC FS 48 kHz
W 0xC03E  0x40          # DAC0 <- ASRCI0
W 0xC040  0x01          # HP0 headphone mode
W 0xC03C  0x40          # DAC0 vol 0 dB

# --- Wait PLL_LOCK | POWER_UP_COMPLETE in 0xC0AB ---
R 0xC0AB  until bit7=1 and bit0=1

W 0xC00D  0x17          # MASTER_BLOCK_EN
W 0xC03B  0x84          # unmute DAC0 (DAC1 stays muted)
```

---

## Quick verification

| Check | How |
|-------|-----|
| I2C alive | Read `0xC000`–`0xC002` → `0x41 0x17 0x87` |
| PLL / power | `0xC0AB`: `PLL_LOCK` and `POWER_UP_COMPLETE` |
| ASRC lock | `0xC0AB`: `ASRCI_LOCK` / `ASRCO_LOCK` once host clocks run |
| SPT lock | `0xC0AB`: `SPT0_LOCK` with valid BCLK/FSYNC |
| Analog | MICBIAS0/1 ≈ 1.63 V; HPOUT0 differential drive on J3; FF mic on J5 |

---

## Alternatives / future knobs

| Topic | Default here | Alternative |
|-------|--------------|-------------|
| Slot width | 16-bit (`SLOT_WIDTH=01`) | 32-bit slots (`00`) if the host I2S peripheral prefers 32-bit packing; keep 16-bit sample significance in the MSBs |
| PLL bypass | Off | `PLL_BYPASS=1` with 24.576 MHz core saves power but halves SigmaDSP MIPS |
| FB mic / ANC | Off | Set `PGA2_EN`, `ADC2_EN`, route ADC2 into FastDSP; still keep ASRC for host I/O |
| Extra mics on J6 | Off | Enable ADC1/ADC3 + PGA as needed |
| DAC low power | Off | `DAC_LPM=1` in `0xC03A` once audio quality is OK |

---

## Board pins vs. registers (summary)

| Schematic net | Codec use | Boot implication |
|---------------|-----------|------------------|
| SCL / SDA | I2C | Pull-ups to +1V8 (R1/R2) |
| BCLK_0 / FSYNC_0 / SDATAI_0 / SDATAO_0 | SPT0 | TDM slave + ASRC |
| PD_N | Hardware PD | Must be high for I2C |
| SELFBOOT | Tied low | No EEPROM boot |
| REG_EN | Tied +1V8 | Internal DVDD LDO; 20 ms wait |
| XTALI / XTALO | 24.576 MHz | `XTAL_EN` + `XTAL_MODE` |
| AIN0 / MICBIAS1 | FF mic | ADC0 + PGA0 + MBIAS1 |
| AIN2 / MICBIAS0 | FB mic | Bias on; ADC off in this image |
| HPOUTP0 / HPOUTN0 | Speaker | `PB0_EN` + `HP0_MODE=1` |
| BCLK_1, FSYNC_1, SDATA*_1, DMIC* | NC | Weak pull-downs |
| HPOUT*1, AIN1, AIN3 | NC / optional | Leave powered off |
