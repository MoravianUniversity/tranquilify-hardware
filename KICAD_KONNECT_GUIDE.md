# KiCad + Konnect Working Guide

Goal: get the same result with fewer LLM turns and fewer tool calls.
Add to this file as new things are discovered.

## 1. Hard rules

- Change KiCad files only through Konnect MCP tools. Never hand-edit `.kicad_*`.
  - The one disclosed exception: a single-value edit of `min_hole_clearance` in `.kicad_pro`.
- Verify every change with readback, ERC (schematic) and DRC (PCB). Do not trust the "success" reply alone.
- Reading files directly (grep, read) is fine and is the cheapest way to find refs, footprints and coordinates.

## 2. Editor locks (the most common time-waster)

- **Schematic:** if the schematic is open in KiCad, there is a lock file (`~*.kicad_sch.lck`).
  Every Konnect schematic write then fails (`stale_target`, `mutation_outcome_uncertain`, or `conflict`).
  - Close the schematic editor BEFORE starting a batch of schematic edits.
  - After a lock failure, grep the file to confirm nothing was written before retrying.
- **PCB:** PCB tools talk to the live KiCad IPC session, so the PCB editor can stay open.
- Workflow tip: batch all schematic changes into one session ("close the schematic, I'll do all edits, then reopen"), instead of interleaving edits and viewing.

## 3. Konnect tool quirks

1. `add_power_symbol` takes `power_net` (e.g. `"GND"`, `"+1V8"`), not `lib_id`.
2. All schematic placement snaps to the 1.27 mm grid. Choose coordinates on the grid up front.
3. There is no DNP-flag tool and no schematic text-delete tool.
   - DNP: put "(DNP)" in the Value, or set the attribute by hand in KiCad.
   - Text deletion: `batch_delete` with the text's uuid works.
4. `batch_edit_schematic_components` takes `{schematic, edits:[{reference, value?, footprint?, fields?}]}`.
   Use it for value, footprint and part-number changes in one call. Set `create_missing: true` to add new custom fields.
5. `batch_delete` takes references and uuids. `list_schematic_wires` returns wire uuids.
6. Prefer the batch tools (`batch_add_wire`, `batch_add_junction`, `batch_place_components`, `batch_connect_pins`, `batch_edit_schematic_components`) over many single calls.
7. `rotate_schematic_component` takes an absolute rotation, not a delta.
8. Orientation facts:
   - Power symbols: rotation 0 points down, 90 extends right, 180 points up, 270 extends left.
   - `Conn_01x04` at rotation 180 puts pins on the right.
   - `Conn_02x03_Odd_Even` with mirror `y` puts odd pins on the right of the origin, even pins on the left.
9. Wire crossings need no junction. Junctions are needed at T-connections and where 3 or more items meet.
10. Net names:
    - Wire-only nets get auto names like `Net-(J4-Pin_1)`.
    - To keep stable net names for the PCB, put a net label on one wire per net.
    - Names show with a `/` prefix in the netlist.
11. `render_schematic_png` writes a PNG next to the schematic. The picture is small, so use it for layout sanity checks and not for pixel-level overlap checks. `check_schematic_overlaps` is better for that.

## 4. Efficient workflow

1. **Plan on paper first.** Decide the full pin map, net names, values, footprints and coordinates before the first tool call.
2. **Read cheaply.** Use grep on the `.kicad_sch` for `Reference`/`Footprint`/`at` lines. Avoid reading whole files or whole PDFs.
3. **Write in batches.** One edit pass per area, with all wires, junctions and power symbols in a handful of batch calls.
4. **Verify once per batch.** Run `run_erc`, then `generate_netlist` to `/tmp` and check the nets with a small Python parser. Use the PNG render only at the end.
5. **PCB sync is a separate step.** Finish the schematic first, then `update_pcb_from_schematic` once. Do not sync after each small schematic edit.
6. **Don't redo work.** Before re-laying out, check whether a change is just a Value/Footprint edit.

## 5. Design preferences (this user)

### Schematic style
- **Drawn nets first, labels sparingly.** Connect with wires by default. The original complaint was a sheet where nets were almost all labels and never drawn.
  A few labels are fine for long runs that would cross the whole sheet (e.g. SDA/SCL/PD_N, or HPOUTP0/HPOUTN0 between J3 and the output stage), and for net-name labels on one wire per net.
- Readable signal flow:
  - Inputs and connectors on the left, IC in the centre, outputs on the right.
  - Mic chains go in horizontal rows, with the bias bus on a vertical line.
- Short notes on the sheet for power, I2C address straps and firmware-side requirements.
- Value fields carry full specs, e.g. `4.7uF X7R 10% 16V`. Crystal Value is the manufacturer part number, with the frequency as a text note beside it.

### Parts and values
- Passives: 0402 for general parts. Larger for DC-biased or high-value caps. Mic coupling caps C16–C19 are 4.7 uF X7R 10% 16V in 0805.
- Ceramic caps: X7R or better, rated at least 1.6× the working voltage (16V for 5V and below).
- Crystal Y1: SX32Y024576DC1T001, 12 pF load, with 18 pF load caps.
- LDO U2: TLV75518PDBV. LDO input filter: FB1 + C22.
- I2C pull-ups: 4.7k to +1V8. Host logic is 1.8 V.
- Unused ADAU1787 inputs are left unconnected. Enable internal pull-downs in firmware for U1 C4, C5 and D5.

### PCB (JLCPCB, 4 layers)
- Via-in-pad is allowed for the WLCSP U1 (ADAU1787BCBZ).

## 6. Ways to reduce LLM usage

- Give the whole change list in one message ("do these 5 things"), rather than a series of small follow-ups.
- Close the schematic editor first, so the first attempt works.
- Tell the assistant when you have edited the file by hand, so it re-reads instead of trusting stale coordinates.
- Make design decisions up front (connector pinouts, parts, voltage ratings), because changing a decision means re-doing wiring.
- Do repetitive, visual work in KiCad yourself (nudging labels, text placement, final cosmetics). Use the LLM for bulk, rule-based edits and verification.
- Ask for specific outputs ("report only ERC/DRC counts") instead of full dumps.
- Reuse this document at the start of new chats.
- Put stable lessons in `.cursor/rules/konnect-quirks.mdc` so they load automatically. This file is the longer reference.
