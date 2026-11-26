# GF180D clock and pump capacitor feasibility

The proposed charge-pump specification budgets 0.50 mm² for the full core and limits the unloaded output to 5.5 V at 3.63 V input. This experiment tests the 100 MHz sizing assumption, the capacitor terminals that experience the stress, and the area still available for the rest of the circuit. It extends the earlier prescribed-clock experiment with an enabled on-chip oscillator and a load release. The specification is awaiting ratification and topology selection is open. [Proposed S1–S9](https://github.com/2AMLogic/gf180-charge-pump/blob/2fe66388da3946c1eafd7b098cd5e20182a6992c/spec/0001-target-spec.md) · [Earlier driver experiment](https://github.com/2AMLogic/gf180-charge-pump/issues/53#issuecomment-7185839875)

## Circuit and load

Three 6 V transistor stages form an enabled ring. A NAND holds the ring in a defined DC state until enable rises at 100 ns. Three 8 × 8 µm MIM capacitors set the delay. Each timing node also carries an assumed 5 fF of wire load. Tapered 3.3 V CMOS inverters drive the two pump phases. Both phases come from the ring. Each final inverter sees its flying bank and the switching load of the pump. The two 56-unit flying banks and the 109-unit reservoir use the 40 × 40 µm GF180D M4/M5 model. Separate capacitors model a nominal 1% parasitic at each pumped node. Both pump PMOS bodies connect to the output. [SPICE circuit](candidate.spice)

The clock rail is an ideal external supply at 2.97, 2.85 and 2.80 V for input voltages of 2.97, 3.30 and 3.63 V. A behavioral shunt with a 5.45 V threshold and 1 Ω on-slope supplies the output limiting. The clock rail, shunt, routing and body-current paths still need physical implementations. The pump is enabled with a 1 GΩ leakage path. The independent current load ramps from zero to 10 mA over 2–12 µs, holds 10 mA until 22 µs, ramps down over 100 ns and stays released through 24 µs. The 135 points comprise all five MOS process corners, three MIM corners, three temperatures and three input supplies.

## Clock and output

| Measurement with the external shunt enabled | Across corners |
|---|---:|
| Startup clock, both final phases (135 corners) | 117.37–360.29 MHz |
| Sustained clock, both final phases at 10 mA (135 corners) | 117.39–359.98 MHz |
| Output throughout the 10 µs load ramp (135 corners) | 4.771–5.474 V |
| Output throughout the following 10 µs at 10 mA (135 corners) | 4.764–5.464 V |
| Peak-to-peak ripple in the final 2 µs at 10 mA (135 corners) | 23.47–43.03 mV |
| Maximum unloaded output before the ramp (30 high-input, hot/cold corners) | 5.47368 V |
| Maximum during load release and the next 1.9 µs (same 30 corners) | 5.47380 V |

All 135 traces meet the proposed S2/S3 loaded band and S5 ripple limit in the measured windows. All 30 proposed S8 corners stay within the 5.5 V ceiling with the ideal-reference shunt present. The highest output at any instant across all 135 complete traces is 5.47385 V. The worst loaded floor occurs at slow MOS, low MIM, 125 °C, 2.97 V input. The lowest sustained frequency occurs at slow MOS, high MIM, 125 °C, 3.63 V input.

The clock period comes from twenty rising-edge intervals at half the driver rail on each final phase output. At the slow/hot, high-input, high-capacitance point, raising the three timing capacitors from 8 × 8 µm to 9 × 9 µm reduces the loaded clock to **99.07 MHz**. The oscillator therefore needs a physical timing budget or trim. Variation of its prescribed rail, extracted delay wiring and the complete regulator are outside this screen. [Startup clock records](records/clock.json) · [Loaded transients](records/load.json) · [Controls](records/controls.json)

## MIM terminals and published ratings

| Observed voltage over the complete 24 µs run with shunt | Minimum (V) | Maximum (V) |
|---|---:|---:|
| Flying bank A, boosted plate minus clock plate | −1.329 | 3.344 |
| Flying bank B, boosted plate minus clock plate | −2.945 | 3.405 |
| Boosted plate A to ground | −0.958 | 5.893 |
| Boosted plate B to ground | −0.991 | 5.945 |
| Clock A to ground | −0.020 | 2.952 |
| Clock B to ground | −0.093 | 3.082 |
| Reservoir to ground | 0.00017 | 5.474 |
| Three grounded timing MIMs (combined) | −0.019 | 2.997 |

The stored flying-capacitor measurements use the signed instantaneous differences `V(a) − V(clk)` and `V(b) − V(clkb)`, including startup and release. Ground-referenced excursions for all four pins are recorded independently. For the reservoir the lower plate is grounded, so the differential is exactly VOUT. All three grounded timing MIMs are also measured.

**S6 and numerical sensitivity.** Below-ground pumped-node excursions reach −0.991 V across the grid. A separate Gear-2 run at 0.05 ns also reaches −0.983 V in the high-input, cold, FS control. The raw PMOS well-source probe includes junction displacement and numerical ringing. At nominal conditions its largest absolute transient current changes from 19.47 A (default trapezoidal, 0.1 ns cap) to 2.06 A (trapezoidal, 0.05 ns) and 85.9 mA (Gear-2, 0.05 ns). Across those three integrations the loaded clock is 209.23–209.42 MHz, full-trace output maximum 5.4636–5.4640 V and settled ripple 26.49–26.86 mV. The cold, open-shunt Gear control still reaches 6.235 V across the reservoir and 3.605 V maximum across the flying MIMs. Physical well resistance, qualified junction limits, extracted loads and integration convergence are required to evaluate device reliability. [Integration controls and settled well currents](records/gear.json)

| MIM option | Pinned model application ceiling across its plates | Foundry electrical table, maximum operating voltage across the capacitor |
|---|---:|---:|
| 1.0 fF/µm² | 20 V | 20 V |
| 1.5 fF/µm² | 6 V | 10 V |
| 2.0 fF/µm², used here | 6 V | 6.6 V |

The comparisons above retain the **6 V model application ceiling** used by the proposed spec. The foundry table gives higher electrical maxima for two options and restricts a process flow to a single MIM type. Its breakdown measurements are separate quantities. The pinned open_pdks installation and the source device-list header distinguish voltage *across* the two plates from either pin's voltage to substrate. [Foundry electrical table](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_6_4.html) · [PDK model header, lines 89–91](https://github.com/efabless/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/aacc04cc30ed119baaa616dff266cca7006dc3d6/models/ngspice/sm141064.ngspice#L89-L91)

With the shunt disabled at 3.63 V input and fast MOS / low MIM, the reservoir reached **6.239 V at −40 °C** and **6.219 V at 125 °C**. Both violate S8 and exceed the pinned model's 6 V application range. These out-of-range voltages are negative-control indications, with magnitude subject to model validity. In the cold run the higher pumped plate reached **6.370 V to ground** and the largest flying-capacitor differential was **3.607 V**. An absolute boosted-node comparison would misclassify the flying banks and miss the distinct limiting requirement on the reservoir. [Control transients](records/controls.json)

## S7 capacitor area

The spec's 100 MHz first-order calculation requires about 139 pF flying and 500 pF output at minimum capacitance, roughly 0.36 mm² of active plates at 1.791 fF/µm². The candidate uses a different split. Its 1 kHz, 25 °C AC measurement gives **162.40 pF per flying bank and 316.09 pF output** in the low-capacitance corner. Typical values are 180.44 pF and 351.21 pF. The independent AC check verifies each bank against a single unit and measures the 8 µm timing capacitor at 0.1215–0.1485 pF across the MIM corners. [AC measurements](records/capacitance.json) · [Original area calculation](https://github.com/2AMLogic/gf180-charge-pump/blob/2fe66388da3946c1eafd7b098cd5e20182a6992c/spec/0001-target-spec.md)

The 221 large plates and three timing plates occupy **0.353792 mm²** of drawn active plate area. The PDK PCell coupon packs the large units in a 17 × 13 array with 42.4 µm pitch. The 221-unit outline measures 719.6 × 550.0 µm. A column of three timing units expands it to **730.0 × 550.0 µm, or 0.401500 mm²**, leaving **0.098500 mm²** of the proposed S7 budget for every other component and its routing. The native MIM-B deck checked all twelve MIM rule categories and reported zero markers. Full standalone variant-D DRC reported one each for DCF.1b, PL.8, M1.4, M2.4 and M3.4. These are separate, unwired PCells. The switches, driver/oscillator placement, current handling, shunt, regulator, guard rings, fill and full block LVS still determine the finished footprint. [Footprint producer](footprint.py) · [Prior packing coupon](https://github.com/2AMLogic/gf180-charge-pump/issues/54#issuecomment-7185647221)

## Reproduction

Use ngspice 46, Python 3, and the GF180MCU-D Ciel build of open_pdks `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`. Set `GF180_PDK_PATH` to the variant directory. Each run checks the four model-file digests and records the SHA-256 of the candidate circuit. Each point must return every finite measurement. Run from the repository root. Output can be redirected for comparison with the JSON records.

```sh
python3 sim/clock-cap-screen/screen.py capacitance
python3 sim/clock-cap-screen/screen.py clock
python3 sim/clock-cap-screen/screen.py load
python3 sim/clock-cap-screen/screen.py controls
python3 sim/clock-cap-screen/screen.py gear
```

The default is one simulator process. On a dedicated machine, `--jobs N` runs independent corners concurrently. To reproduce the measured coupon and its native MIM DRC, use a new output pathname and the pinned installation's PCell library.

```sh
uv run --no-project --with 'klayout==0.30.13' python sim/clock-cap-screen/footprint.py /tmp/pump-cap-coupon.gds
klayout -b -r "$GF180_PDK_PATH/libs.tech/klayout/tech/drc/gf180mcu.drc" \
  -rd input=/tmp/pump-cap-coupon.gds -rd report=/tmp/pump-cap-mim.lyrdb \
  -rd variant=D -rd topcell=CAPACITOR_COUPON -rd decks=mim_b
```

Omit `-rd decks=mim_b` for the standalone full-deck measurement.
