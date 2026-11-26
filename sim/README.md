# sim

Testbenches and PVT corner results (ngspice). `harness/` is the generic
sim-harness-core (see `harness/README.md`) plus `harness/pump_evidence.py`.

## Bench index

| slug | what it measures | files |
|---|---|---|
| `device-stress/` | per-device Vds/Vgs/Vdb/Vsb/Vgb maxima over the full transient vs the rating, at full load | `testbench/` |
| `load/` | steady Vout and ripple into a resistive load (10 mA at 4.5 V) | `testbench/` |
| `load-step/` | Vout min/settled and peak Vds through a 10 us ramp to full load | `testbench/` |
| `startup/` | enable-to-4.5 V time at full load | `testbench/` |
| `cap-model/` | flying-cap model extraction (MIM vs MOS cap); `records/` is append-only | `extract.py` |

All four benches share one corner set: `mos_mimcap` (tt/ff/ss/fs/sf; `tt` maps
to the PDK's `typical` section) x (`mimcap_typical`/`mimcap_ss`/`mimcap_ff`) x
-40/25/125 C x 3.3 V +/-10 % = 135 points.

**The DUT is a parameter.** `benches/dut_reference.spice` is a bench bring-up
doubler, *not the design*, and does not meet the spec. `benches/generate.py`
assembles it with each stimulus into `<slug>/testbench/netlist.spice` and writes
`tb.json` (the harness forbids `.include` in a fragment); `python3
benches/generate.py --check` fails on drift. Swapping in the real topology (#1)
means editing `dut_reference.spice` and `DEVICES`.

Placeholders (flagged in `generate.py`; change a value when #1 ratifies): 6.0 V
device rating (**unconfirmed**; the PDK names these "6.0V" devices and carries no numeric rating, so the name-plate is used unpadded), ripple limit,
start-up time limit.

## Records

`records/` is the append-only home for suite-level measurement records (for
example `records/ngspice-sensitivity.md`), as distinct from
`cap-model/records/`, which is that bench's own evidence.

## Running

```
python3 -m harness.cli list
python3 benches/single_point.py device-stress      # ONE point, local debug probe
python3 -m unittest tests.test_benches
```

The full 135-point grid is a `klt sim` batch request (`--wait-for-capacity 600`),
not a local loop. The harness `run` fans out locally, so do not use it on a
shared worker for the whole grid.

## PDK finding

`sm141064.ngspice` selects the same `nfet_06v0_t` / `pfet_06v0_t` model *cards*
in every process section (tt/ff/ss/fs/sf), but each section first sets different
skew `.param`s that those cards consume (`nfet_06v0_vth0`, `_vsat`, `_xl`/`_xw`,
`_tox`, `_cgso`/`_cgdo`, `pfet_06v0_dvth0`, `_dxl`/`_dxw`/`_dtox`, ...). The 6 V
devices therefore **do** vary with the process corner. Measured on the bring-up
DUT (`load`, 25 C, 3.3 V, 10 mA-sized resistor): mean Vout 2.589 V (tt),
3.011 V (ff), 2.139 V (ss), a 0.87 V spread from the process corner alone.
The process corner is a first-order axis for this block; do not skip it or
dismiss a corner-driven failure.
