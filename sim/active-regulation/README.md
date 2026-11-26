# Charge pump with transistor-level output and clock-rail regulation

This candidate replaces the prescribed oscillator supply and the 5.45 V behavioral shunt in the [clock and capacitor experiment](../clock-cap-screen/README.md). Its external sources are VIN, the logic enable, and the test load. A GF180D bandgap supplies two error amplifiers. One controls a PMOS series pass bank on the oscillator rail, and the other drives a 6 V NMOS output shunt. The proposed specification and topology are awaiting operator decisions. [Proposed S1–S9](https://github.com/2AMLogic/gf180-charge-pump/blob/2fe66388da3946c1eafd7b098cd5e20182a6992c/spec/0001-target-spec.md)

## Circuit

The bandgap uses ten 5 × 5 µm vertical PNP units in an explicit 1:8:1 ratio, a resistor-weighted PTAT voltage, and a 700-square poly startup bleed. The oscillator supply uses a 1,600 µm total-width thin-oxide PMOS with a local bank of sixteen 40 × 40 µm MIMs. The shunt uses a 1,200 µm total-width thick-oxide NMOS and a high-voltage poly 32:10 divider. The lower nominal output target, approximately 5.0 V, leaves headroom for the shunt's finite response. Both regulators draw current whenever VIN is applied. EN controls the oscillator. The parent switch widths, body ties, pump capacitors, assumed wiring and plate parasitics are retained. [Device circuit](regulators.spice) · [Integrated deck and probes](screen.py)

## Integrated load and release

At 3.30 V, typical process and 25 °C, the integrated candidate sustained a 4.98568 V floor through 10 µs at 10 mA. The maximum during load release was 5.07176 V. Its shunt dissipated 29.08 mW at full load and 79.00 mW at no load. The most forward-biased sampled MOS junction reached 0.895 V, and the thin-oxide family reached 3.30010 V drain-to-source. A separate 1 µs supply ramp with EN rising at 1.5 µs produced a 4.98577 V loaded floor and 5.07207 V release peak. [Nominal run](records/smoke.json) · [Half-step, supply-ramp and cross-passive controls](records/controls.json)

The full screen measures 65 cases over the proposed MOS/temperature/VIN grid, with all three MIM corners at each high-input, hot/cold point. The resistor and bipolar corners track fast and slow MOS in the primary grid. The two crossed controls reverse both passive corners together. These simulations use Gear-2 and retain the greatest excursion of each gate, drain, source and body terminal pair over the complete 24 µs trace, together with the contributing instance. Positive body-forward values orient the junction for the MOS polarity. The 3.3 V and 6 V nameplates provide conservative comparisons; source/drain injection, lifetime, and current density require physical evidence. The circuit has no extracted well or interconnect resistance.

The 65 independent 24 µs transients all completed. During the full 10 µs
hold at 10 mA, VOUT spans **4.69170–5.10574 V** across all cases. The
worst peak-to-peak swing over one hold is **36.57 mV**, at FS MOS, fast MIM,
125 °C and 3.63 V. The largest load-release peak is **5.44194 V**, at slow
MOS/MIM/resistor/bipolar, 25 °C and 2.97 V. Across the 30 high-input
hot/cold cases the largest output anywhere on the 24 µs trace is
**5.23716 V**. The nominal row reproduces the standalone nominal record
exactly. These tests measure the proposed output voltage, load, ripple and
no-load ceiling on the schematic. [All 65 cases](records/pvt.json)

Stress and dissipation still constrain this design. The maximum thick-oxide
terminal differential is 5.74246 V. Its most forward-biased drain/body
junction reaches 0.97831 V. The largest thin-oxide drain/body differential
is 3.64875 V, and 50/65 cases have a thin-oxide terminal pair greater than
3.3 V. No-load shunt dissipation reaches 131.535 mW. The measurement needs
a foundry-supported junction-current and duration limit, body-tie extraction
and a thermal assessment before the device-stress claim can close.

Removing the shunt lets the fast/cold 3.63 V output reach 6.27646 V.
With both feedback paths intact, a 1 ns load edge yields a 4.84411 V loaded
floor and 4.90318 V release peak there. At slow/hot 2.97 V the same edge
gives 4.69170 V and 5.41617 V. Forcing the clock driver to VIN at the
slow/hot point raises the floor to 4.81138 V and the peak to 5.42891 V.
[Isolation and load-edge controls](records/isolation.json)

## Output shunt response

The disturbance is a 10 mA increase from 5 to 15 mA in 1 ns. The peak result is the positive output excursion divided by 10 mA. The AC result is the magnitude of the bare shunt impedance at 15 mA. Eleven runs cover the nominal point and each high-input, hot/cold MOS corner with its tracking passive models.

| Measurement | Nominal | Range |
|---|---:|---:|
| Bare shunt, settled step (Ω) | 0.403 | 0.292–2.625 |
| Bare shunt, peak step (Ω) | 20.396 | 16.288–26.975 |
| With 109 reservoir MIMs, peak step (Ω) | 15.864 | 12.568–21.043 |
| Bare shunt, 1 kHz (Ω) | 0.287 | 0.212–0.746 |
| Bare shunt, 1 MHz (Ω) | 3.190 | 1.711–6.319 |
| Bare shunt, 10 MHz (Ω) | 15.908 | 11.182–22.542 |
| Bare shunt, 100 MHz (Ω) | 18.053 | 14.717–23.622 |

The former 5.45 V threshold experiment bracketed the release limit with a frequency-independent 2–4 Ω shunt. Its on-slope does not describe this transistor circuit at switching frequencies. The actual shunt's setpoint, reservoir and driver response all enter the integrated transient. The bare shunt measurements also include 5 mA and 30 mA AC bias and six frequencies up to 300 MHz. [Parent impedance control](https://github.com/2AMLogic/gf180-charge-pump/pull/65#issuecomment-7197046055) · [Stand-alone shunt bench](impedance.py) · [Measurements](records/impedance.json)

## Host programming pulses

The [transient runner](host_pulses.py) drives the transistor pump with three consecutive 10 mA flat-top loads. Each has 1 ns leading and trailing edges. The simulation includes startup, short recovery intervals and a final enabled-idle window. Cases are typical/25 °C/3.30 V, slow/125 °C/2.97 V and fast MOS with slow MIM/−40 °C/3.63 V. The third case uses fast resistor and bipolar sections. Release is the maximum during the first microsecond following the flat top. Efficiency is the ratio of mean load power to mean input power over each flat top. [Signed source measurements and circuit hashes](records/host-pulses.json) · [Raw ngspice 46 output for all three cases](records/host-pulses)

| Flat top | Loaded voltage across three corners | Highest release | Loaded efficiency |
|---|---:|---:|---:|
| 1 µs | 4.69170–5.11905 V | 5.39415 V | 19.41–59.49% |
| 10 µs | 4.69170–5.12874 V | 5.39402 V | 19.43–58.71% |
| 100 µs | 4.69170–5.13361 V | 5.39416 V | 19.43–58.64% |

Across those conditions, 9/9 pulses stay within the proposed loaded voltage range and below or at the release ceiling. The largest final-idle input and shunt power were 250.27 mW and 131.54 mW. The applied load is an ideal current sink representing the host demand. Routing parasitics, electrothermal effects, the actual eFuse program path and the remaining PVT combinations need their own checks.

## Capacitor floorplan

The GF180D PCell coupon contains 241 squares of 40 µm, one of 26 µm, one of 20 µm and three of 8 µm. All physical MIMs from both schematics are included. The active plate area is 0.386868 mm². Their 19-column placement measures **804.4 × 550.0 µm, or 0.442420 mm²**. The remaining 0.057580 mm² of the 0.50 mm² proposal would have to accommodate the MOS devices, PNPs, resistors, routing, guards and fill. The array is unwired. It has no full-core LVS or current-handling result.

The native MIM-B run checked all 12 rule categories and returned zero violations. Full native GF180D DRC checked 768 categories and reported five individual markers, DCF.1b, M1.4, M2.4, M3.4 and PL.8. The full coverage assertion accounts for the 763 empty-layout declarations and these five geometry-conditional density declarations. KLT 0.9.2 records KLayout 0.30.14 as a version mismatch to its tested 0.30.12; the exact engine and deck hashes are preserved. [Coupon GDS](records/capacitors.gds) · [DRC receipts](records/coupon-drc.json)

## Reproduce

Use the repository's GF180MCU-D open_pdks build `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`, ngspice 46, and a Python 3 environment. Set `GF180_PDK_PATH` to the variant directory. Both SPICE programs check the four model-file hashes. The core and regulator hashes identify the integrated circuit. Run the following from the repository root. The default is one simulator worker, and `--jobs N` changes the number of parallel corners.

```sh
python3 sim/active-regulation/screen.py smoke
python3 sim/active-regulation/screen.py pvt
python3 sim/active-regulation/screen.py controls
python3 sim/active-regulation/screen.py isolation
python3 sim/active-regulation/impedance.py
python3 sim/active-regulation/host_pulses.py --jobs 3 --log-dir /tmp/pump-host-pulses
uv run --no-project --with 'klayout==0.30.14' python sim/active-regulation/coupon.py /tmp/active-reg-coupon.gds
uv run --no-project --python 3.12 --with 'klayout-tools==0.9.2' --with 'klayout==0.30.14' python sim/active-regulation/check_coupon.py /tmp/active-reg-coupon.gds
```

Place native KLayout 0.30.14 on PATH for the DRC command. The coupon generator requires a fresh output path and disables GDS timestamps.
