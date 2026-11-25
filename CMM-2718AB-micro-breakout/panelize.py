"""
Panelize 2x CMM-2718AB-micro-breakout (4.8x6mm) with 2x CMM-2718AB-breakout
(11.5x13.5mm) into one panel sized at least 70x70mm for JLCPCB Standard PCB Assembly.

Both source boards must use the same PCB thickness (0.6mm).

Run with KiCad's Python (KiKit is installed there):

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 panelize.py
"""

from itertools import chain
from pathlib import Path
import tempfile

from kikit import panelize_ui_impl as ki
from kikit.panelize import Panel, Origin
from kikit.units import mm
from pcbnew import LoadBoard, SaveBoard, VECTOR2I

HERE = Path(__file__).resolve().parent
REGULAR_PCB = HERE.parent / "CMM-2718AB-breakout" / "CMM-2718AB-breakout.kicad_pcb"
MICRO_PCB = HERE / "CMM-2718AB-breakout.kicad_pcb"
OUTPUT_PCB = HERE / "combined_panel.kicad_pcb"

# Board sizes (Edge.Cuts) and panel spacing
REGULAR_W, REGULAR_H = 11.5 * mm, 13.5 * mm
GAP = 2.5 * mm

# JLCPCB Standard Assembly target thickness for this combined panel.
# Source boards currently disagree (regular 1.6mm, micro ~0.5mm); KiKit requires
# matching thickness, so we panelize from temporary copies normalized to this.
PANEL_THICKNESS = int(0.6 * mm)


def normalize_thickness(src: Path, dst: Path, thickness: int) -> None:
    board = LoadBoard(str(src))
    board.GetDesignSettings().SetBoardThickness(int(thickness))
    SaveBoard(str(dst), board)

# Match panel-2x2-options.json, plus mintotal* so the frame pads to 70x70mm
PRESET = ki.obtainPreset(
    [],
    tabs={
        "type": "fixed",
        "vwidth": "1.25mm",
        "hwidth": "1.25mm",
        "vcount": "0",
        "hcount": "2",
    },
    cuts={
        "type": "mousebites",
        "drill": "0.45mm",
        "offset": "0.25mm",
    },
    framing={
        "type": "frame",
        "width": "5mm",
        "hspace": "2.5mm",
        "vspace": "2.5mm",
        "mintotalwidth": "70mm",
        "mintotalheight": "70mm",
    },
    tooling={
        "type": "3hole",
        "hoffset": "2.5mm",
        "voffset": "2.5mm",
        "size": "1.152mm",
    },
    fiducials={
        "type": "3fid",
        "hoffset": "5mm",
        "voffset": "2.5mm",
        "coppersize": "1mm",
        "opening": "2mm",
    },
    post={
        "millradius": "1mm",
    },
)


def main() -> None:
    for path in (REGULAR_PCB, MICRO_PCB):
        if not path.is_file():
            raise SystemExit(f"Missing board file: {path}")

    with tempfile.TemporaryDirectory(prefix="cmm-panelize-") as tmp:
        tmp_dir = Path(tmp)
        regular_tmp = tmp_dir / "regular.kicad_pcb"
        micro_tmp = tmp_dir / "micro.kicad_pcb"
        normalize_thickness(REGULAR_PCB, regular_tmp, PANEL_THICKNESS)
        normalize_thickness(MICRO_PCB, micro_tmp, PANEL_THICKNESS)

        board_regular = LoadBoard(str(regular_tmp))
        board_micro = LoadBoard(str(micro_tmp))

        panel = Panel(str(OUTPUT_PCB))
        panel.inheritDesignSettings(board_regular)
        panel.inheritProperties(board_regular)
        panel.inheritTitleBlock(board_regular)

        source_regular = ki.readSourceArea(PRESET["source"], board_regular)
        source_micro = ki.readSourceArea(PRESET["source"], board_micro)

        net_renamer = lambda n, orig: f"Board_{n}-{orig}"
        ref_renamer = lambda n, orig: f"Board_{n}-{orig}"

        # Layout (TopLeft origins), regulars on the left, micros on the right:
        #
        #   [Regular 11.5x13.5]  [Micro 4.8x6]
        #   [Regular 11.5x13.5]  [Micro 4.8x6]
        #
        # Micros are vertically centered in each regular-board row.
        micro_x = REGULAR_W + GAP
        row_pitch = REGULAR_H + GAP
        micro_y_pad = (REGULAR_H - 6.0 * mm) // 2

        placements = [
            (regular_tmp, source_regular, VECTOR2I(0, 0)),
            (regular_tmp, source_regular, VECTOR2I(0, int(row_pitch))),
            (micro_tmp, source_micro, VECTOR2I(int(micro_x), int(micro_y_pad))),
            (micro_tmp, source_micro, VECTOR2I(int(micro_x), int(row_pitch + micro_y_pad))),
        ]

        substrate_count = len(panel.substrates)
        for i, (path, source_area, dest) in enumerate(placements):
            panel.appendBoard(
                str(path),
                dest,
                origin=Origin.TopLeft,
                sourceArea=source_area,
                netRenamer=net_renamer,
                refRenamer=ref_renamer,
                inheritDrc=(i == 0),
                tolerance=1 * mm,
            )

        substrates = panel.substrates[substrate_count:]
        framing_substrates = ki.dummyFramingSubstrate(substrates, PRESET)
        panel.buildPartitionLineFromBB(framing_substrates)
        backbone_cuts = ki.buildBackBone(PRESET["layout"], panel, substrates, PRESET)

        tab_cuts = ki.buildTabs(PRESET, panel, substrates, framing_substrates)
        frame_cuts = ki.buildFraming(PRESET, panel)

        ki.buildTooling(PRESET, panel)
        ki.buildFiducials(PRESET, panel)
        for text_section in ("text", "text2", "text3", "text4"):
            ki.buildText(PRESET[text_section], panel)
        ki.buildPostprocessing(PRESET["post"], panel)

        ki.makeTabCuts(PRESET, panel, tab_cuts)
        ki.makeOtherCuts(PRESET, panel, chain(backbone_cuts, frame_cuts))

        ki.buildCopperfill(PRESET["copperfill"], panel)
        ki.setStackup(PRESET["source"], panel)
        ki.setPageSize(PRESET["page"], panel, board_regular)
        ki.positionPanel(PRESET["page"], panel)
        ki.runUserScript(PRESET["post"], panel)
        ki.buildDebugAnnotation(PRESET["debug"], panel)

        panel.save(reconstructArcs=PRESET["post"]["reconstructarcs"])
        bbox = panel.boardSubstrate.bounds()
        width_mm = (bbox[2] - bbox[0]) / mm
        height_mm = (bbox[3] - bbox[1]) / mm
        print(f"Wrote {OUTPUT_PCB}")
        print(f"Panel size: {width_mm:.2f} x {height_mm:.2f} mm")
        print(f"Panel thickness: {PANEL_THICKNESS / mm:.2f} mm (sources normalized for KiKit)")


if __name__ == "__main__":
    main()
