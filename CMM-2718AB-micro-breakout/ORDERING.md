Ordering Notes
==============

Each individual breakout board is 4.8x6mm. The regular breakout board is 11.5x13.5mm.

Need to panelize the PCBs first to make it at least 70x70 mm (for Standard PCB Assembly). For this at least we can combine the micro and regular breakout boards together.

```bash
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 panelize.py
# writes combined_panel.kicad_pcb (2x regular + 2x micro, 70x70mm frame, 0.6mm)
```

# Basics
- Base Material: MFR-4
- Layers: 2

# PCB Specifications
- Deburring/Edge Routing: Yes
- Different Designs: 2  (combined panel: regular + micro breakouts)
- Delivery Format: Single PCB
- PCB Thickness:
    * 0.4mm (ultra thin, costs way more)
    * 0.6mm (for some more rigidity, costs only slight more than standard, does not support Economical PCB Assembly)
- Surface Finish: ENIG (not HASL since that can leave bumps breaking the seal on the microphone; does add significant cost)
- Gold Thickness: 1 U"

# High-Spec Options
- Via Covering: Tented
- Min via hole size/diameter: 0.3mm


Economical PCB Assembly Options
================================

Same as above, but only need to have the boards panelized to at least 10x10 mm:

```bash
kikit panelize -p panel-2x2-options.json CMM-2718AB-breakout.kicad_pcb panel.kicad_pcb
```

Same settings except:
- PCB Thickness: 0.8mm (minimum for economy)
- Surface Finish: HASL (lead-free; EING is not supported except for 1.6mm thickness)
  * Is OSP supported? It will be flatter than HASL and cheaper than ENIG


Parts Notes
===========
- Have to pre-order CMM-2718AB-38164W-TR, min quantity 400+ (but <2 cents each)
- All other parts are selected and regularly in stock, saved in the BOM file
