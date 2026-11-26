"""Pack all regulator and pump MIMs into an unrouted GF180D capacitor coupon."""

import argparse
from collections import Counter
from pathlib import Path
import sys

import klayout.db as db

import screen


def drawn_units():
    counts = Counter()
    for line in (
        screen.ORIGINAL.read_text() + "\n" + screen.REGULATORS.read_text()
    ).splitlines():
        fields = line.split()
        if (
            not fields
            or not fields[0].startswith("x")
            or "cap_mim_2f0_m4m5_noshield" not in fields
        ):
            continue
        args = dict(f.split("=", 1) for f in fields if "=" in f)

        def size(field):
            value = args[field]
            return 8 if value == "{delay_side}" else int(value.removesuffix("u"))

        length, width = size("c_length"), size("c_width")
        if length != width:
            raise ValueError("The coupon expects square MIMs")
        counts[length] += int(args.get("m", 1))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Supply a new GDS output path")
    pdk = screen.pdk.find_pdk(screen.HERE.parent)
    sys.path.insert(
        0, str(pdk.path / "libs.tech/klayout/tech/pymacros/klayout_api_cells")
    )
    from draw_cap_mim import draw_cap_mim

    sizes = drawn_units()
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("ACTIVE_REG_CAP_ARRAY")
    pitch = 42400
    col_count = 19
    index = 0
    for side, count in sorted(sizes.items(), reverse=True):
        unit = draw_cap_mim(layout, side, side, "MIM-B", "M5")
        box = unit.bbox()
        for _ in range(count):
            x = (index % col_count) * pitch - box.left
            y = (index // col_count) * pitch - box.bottom
            top.insert(db.CellInstArray(unit.cell_index(), db.Trans(x, y)))
            index += 1
    opts = db.SaveLayoutOptions()
    opts.gds2_write_timestamps = False
    layout.write(str(args.output), opts)
    box = top.bbox()
    print(
        f"{dict(sorted(sizes.items()))}: {box.width() * layout.dbu:g} × {box.height() * layout.dbu:g} µm; "
        f"{box.area() * layout.dbu**2 / 1e6:.6f} mm²; {sum(s * s * n for s, n in sizes.items()) / 1e6:.6f} mm² of plates"
    )


if __name__ == "__main__":
    main()
