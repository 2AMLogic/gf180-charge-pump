"""Pack the pump and timing MIMs using the installed GF180D M4/M5 PCell."""

import argparse
import sys
from pathlib import Path

import klayout.db as db

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from harness import pdk  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new GDS path for the isolated capacitor coupon")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    lib = pdk.find_pdk(HERE.parent).path / "libs.tech/klayout/tech/pymacros/klayout_api_cells"
    sys.path.insert(0, str(lib))
    from draw_cap_mim import draw_cap_mim

    layout = db.Layout()
    layout.dbu = 0.001
    pump = draw_cap_mim(layout, 40, 40, "MIM-B", "M5")
    timing = draw_cap_mim(layout, 8, 8, "MIM-B", "M5")
    top = layout.create_cell("CAPACITOR_COUPON")
    top.insert(
        db.CellInstArray(
            pump.cell_index(), db.Trans(), db.Vector(42400, 0), db.Vector(0, 42400), 17, 13
        )
    )
    before = top.bbox()
    # The large-cap coupon has 1.2 um clear between adjacent PCell outlines.
    x = before.right + 1200 - timing.bbox().left
    y = before.bottom - timing.bbox().bottom
    top.insert(
        db.CellInstArray(
            timing.cell_index(), db.Trans(x, y), db.Vector(0, 10400), db.Vector(10400, 0), 3, 1
        )
    )
    after = top.bbox()
    layout.write(str(args.output))
    for desc, box in (("221 pump capacitors", before), ("with three timing capacitors", after)):
        print(
            f"{desc}: {box.width() * layout.dbu:g} x {box.height() * layout.dbu:g} um, "
            f"{box.area() * layout.dbu**2 * 1e-6:.6f} mm^2"
        )


if __name__ == "__main__":
    main()
