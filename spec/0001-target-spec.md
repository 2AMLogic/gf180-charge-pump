# 0001 — Target specification for the on-die program-supply charge pump

Status: RATIFIED

Effective only after both independent reviews, operator approval of the reviewed commit, and merge under §7.

Issue: #1. Classification: changes spec rows and bounds, so both the EE review
and the market review apply (CLAUDE.md, Ratification).

This record defines proposed acceptance criteria for a programming supply for on-die OTP. The calculations in §3 guide sizing. The candidate measurements below are schematic and capacitor-layout evidence. Topology selection and acceptance of a routed core remain open.

## 1. Inputs inherited, and what is not known

The host eFuse spec assumes 5.0 V ±10% (A1), at least 10 mA through the program path (A2), and a nominal 10 µs pulse with a controller range of 1–100 µs (A3). The host identifies these values as assumptions and provides no PDK programming guarantee. S3 keeps the nominal minimum. Interface qualification must also exercise both endpoints of the advertised controller range under S2 and S6. [Host program supply, current and pulse rows](https://github.com/2AMLogic/gf180-efuse-otp/blob/d6399af39bad891b24b7b45cd93d1f8aeb6a0aa6/spec/efuse-otp.md)

## 2. Proposed specification table

Every output-voltage row states its load current and corner.

| # | Parameter | Proposed target | Load / corner | Basis |
|---|---|---|---|---|
| S1 | Input supply | 2.97-3.63 V (3.3 V ±10%) | all | README draft |
| S2 | Output voltage | 4.5-5.5 V | I_load = 10 mA, all 135 MOS × MIM × temperature × supply cases in S9 | inherited A1; upper bound also set by §4 |
| S3 | Load current | ≥ 10 mA, continuous for ≥ 10 µs | at S2 voltage, worst corner | inherited A2/A3 |
| S4 | Enable to output in spec | ≤ 10 µs | discharged reservoir, stable S1 input, EN rising, load initially zero, worst corner | measure time to entering [4.5, 5.5] V and staying in band until load application; test the subsequent 0 → 10 mA step separately |
| S5 | Output ripple | ≤ 100 mV p-p | I_load = 10 mA, worst corner | README draft; sets output capacitance (§3) |
| S6 | Device stress | all gate, drain-source and body-junction differentials within §4 limits, transients included | all corners, including unloaded and switching at VDD = 3.63 V | §4 |
| S7 | Core area (footprint including all capacitors) | **≤ 0.50 mm²** (draft: 0.25 mm²) | n/a | §3; **proposed change to a draft row** |
| S8 | No-load behaviour | output ≤ 5.5 V with EN high and no load | VDD = 3.63 V, hot and cold | §4; an unloaded doubler reaches 2·VDD = 7.26 V |
| S9 | Verification corners | TT/FF/SS/FS/SF MOS × typical/slow/fast MIM density × −40/25/125 °C × 2.97/3.30/3.63 V (135 combinations) | Apply to S2–S6. S8 uses the 30 high-input hot/cold combinations. | §3.1 sizing uses minimum MIM density. |

Use the pinned GF180D MIM model section for each density point. For the baseline MOS rows track resistor and bipolar sections with slow/fast MOS and use their typical sections for TT/FS/SF. Independently cross the supported resistor and bipolar extremes at the regulating and startup limits, retaining any worse result. Document device-model correlations.

Stretch rows (programmable 4.0-5.5 V, ≥ 20 mA, ≤ 2 µs enable, ≤ 25 mV ripple,
≤ 0.10 mm²) are **not proposed for ratification here**. §3 shows ≥ 20 mA and
≤ 25 mV ripple each at least double the capacitance, so ≤ 0.10 mm² cannot
coexist with them. They stay in the README as named, unsized stretch items.

### Which row governs when load and area conflict

**The load row (S3) and ripple row (S5) govern; the area row moves.** The
sizing below shows 10 mA at ≤ 100 mV ripple cannot fit 0.25 mm² at any clock
rate this record considers reachable. S7 is therefore proposed at ≤ 0.50 mm²,
an integration budget. The first-order example at 100 MHz leaves 0.14 mm² for overhead. The 65-case transistor candidate oscillates above 100 MHz throughout its sampled grid. Its actual capacitor placement leaves only 0.057580 mm² for everything else. A full routed implementation must meet S3, S5 and S7 together. A shortfall returns to the operator for disposition. [Candidate evidence](#candidate-measurements-and-remaining-acceptance-tests)

### What the pump commits to if A1-A3 move

- **A2 (current) rises:** 10 mA is the commitment under S2/S3/S5/S7.
  At 15 mA and 2.97 V, the 1.44 V headroom gives 96 Ω total and 48 Ω
  for the slow-switching limit under §3.1's equal split. At 100 MHz the
  minimum-corner capacitances are 208.3 pF flying and 750 pF reservoir.
  At 1.791 fF/µm² their plates alone occupy **0.5351 mm²**, above S7.
  Even with zero switch and routing area the minimum clock would exceed
  107 MHz. A higher current therefore requires a new decision checking
  achievable clock over PVT, full footprint, ripple and terminal stress.
- **A3 (duration) shortens or lengthens:** the continuous pump is unchanged,
  but independence from duration must be measured with the host’s 1, 10 and 100 µs loads, including both edges and the subsequent open load. A duration short enough to make a
  pulsed reservoir viable is the separate candidate in §3.2, not a change to
  S3.
- **A1 (voltage) changes:** S2 covers the stated output band of 4.5–5.5 V.
  A requirement for a regulated lower setpoint needs a new decision; the
  programmable range in §6 is a stretch goal. Outputs above 5.5 V remain
  outside this decision (§4).
- Any change to A1-A3 in gf180-efuse-otp is tracked by that repo's decision
  records; this repo does not edit them.

### Low-current, higher-voltage mode (oxide-breakdown programming)

**Out of scope for this record.** Antifuse programming at µA-to-mA, compliance
limited, would need an output above the 6 V device ceiling (§4), which needs
`nfet_10v0_asym`, which is excluded. It becomes a separate row only after a
DRC-clean 10 V device exists and a decision record admits it.

## 3. First-order capacitance and area sizing

### 3.0 Capacitor density and its source

Source: the PDK ngspice models, `gf180mcuD/libs.tech/ngspice/sm141064.ngspice`
(device list) and `sm141064_mim.ngspice` (parameters), pinned to
`fossi-foundation/open-pdks` commit `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
(`ciel enable --pdk-family gf180mcu`; upstream model repository
`efabless/globalfoundries-pdk-libs-gf180mcu_fd_pr`).

- The shared model library includes several `cap_mim_2f0` layer variants. The GF180D physical candidate uses option B, M4/M5, with five routing metals. Its density model uses `c_cox = 1.99e-3 F/m²`
  × `mim_corner_2p0ff`, i.e. **1.99 fF/µm²** typical. The corner multiplier is
  0.90 (ff) to 1.10 (ss), so the minimum density is **1.791 fF/µm²**.
  Divide the capacitance required at the minimum corner by this density to
  obtain plate area. Equivalently, divide nominal installed capacitance by
  the typical density of 1.99 fF/µm².
  The fringe term (`c_capsw` = 2.38e-10 F/m, about 0.24 fF/µm of perimeter)
  is ignored; this makes the area slightly conservative for large plates.
- The device list header marks `cap_mim_2f0fF` "usable for Volt <= 6 V across
  capacitor". A flying capacitor charged across the supply sees up to 3.63 V
  in that phase. The VOUT-to-ground reservoir sees the full output, up to
  5.5 V at the S2/S8 limit, leaving 0.5 V to the stated 6 V limit. Verify
  the differential voltage across each capacitor during startup, switching
  and load release for the chosen circuit. The topology record also needs
  the bottom-plate parasitic to substrate. The [November 25 extraction
  record](../sim/cap-model/records/20261125-020745.md) measured densities at
  AC small signal. Its comparison of 7.3 V **to ground** with a rating
  **between plates** is inapplicable, including its rejection of the
  1.5 fF/µm² model on that basis. GF180MCU-D selects the 2 fF/µm² MIM option
  in its installed `.config/nodeinfo.json`. The 0.5 V reservoir margin is
  conditional on the VOUT limit holding at every instant. [Corrected model
  extraction and plate ratings](../sim/cap-model/records/20261126-064748.md)
- MOS capacitors (`cap_nmos_06v0`): C is bias-dependent,
  `c = A·(0.001107 + 0.00107·tanh(6.25·V − 4.1875))` F/m² per the model —
  **0.04 fF/µm² at V = 0 V** (0.0375 fF/µm²), **1.11 fF/µm² at the V = 0.67 V
  midpoint**, and **2.18 fF/µm² in strong inversion** (about 10% above
  `cap_mim_2f0` typical). Because capacitance drops nearly 60× between strong
  inversion and 0 V — a rail-to-rail swing spends much of its excursion near
  the 0.04 fF/µm² end, and startup begins at 0 V — while strong inversion gains
  only ~10% over MIM, it is not used for sizing; it stays available for
  DC-biased decoupling.

MIM capacitors sit in upper metal and could in principle be stacked over
circuitry. S7 counts the footprint of everything, with no credit for stacking
over this block's own switches until the layout record shows it DRC/LVS-clean.

### 3.1 Continuous two-phase doubler (the baseline sizing)

Worst-case input is VDD = 2.97 V. An ideal doubler gives 5.94 V. The row S2
floor is 4.5 V at 10 mA, so the total allowed drop is

R_total = (2 × 2.97 − 4.5) V / 10 mA = **144 Ω** (estimate).

Allocate 72 Ω to the slow-switching limit (SSL) and 72 Ω to the effective fast-switching limit (FSL), including conducting switches, routing and vias. The FSL term combines the path resistances at the output, weighted by charge transfer and switching duty. Linear addition is a conservative sizing allocation. Check loaded output, current and ripple directly on the switched circuit and repeat with extracted paths. The ripple formula assumes two interleaved deliveries per period. One delivery per period doubles the reservoir requirement.

SSL output resistance of a doubler with total flying capacitance C_fly at
clock f_sw: R_SSL = 1 / (f_sw · C_fly). The minimum-corner flying
capacitance required by the 72 Ω budget is 1 / (f_sw · 72 Ω).

Each phase delivers charge to the output. The ripple estimate
ΔV ≈ I / (2 · f_sw · C_out) requires C_out = 0.05 / f_sw at the minimum
corner for 10 mA and 100 mV ripple. Divide each required capacitance by
0.9 to obtain the nominal installed capacitances below.

| f_sw | C_fly (nominal) | C_out (nominal) | Plate area at 1.99 fF/µm² typical |
|---|---|---|---|
| 25 MHz | 617 pF | 2.22 nF | 1.43 mm² |
| 50 MHz | 309 pF | 1.11 nF | 0.71 mm² |
| 100 MHz | 154 pF | 0.56 nF | 0.36 mm² |

At 100 MHz the minimum corner requires 138.9 pF flying and 500 pF output.
Their sum divided by 1.791 fF/µm² gives 0.357 mm². The same plates provide
154.3 pF and 555.6 pF nominal at 1.99 fF/µm².

Reading:
- The original body's "hundreds of pF" holds for C_fly alone (154-617 pF), but
  the **output capacitance for 100 mV ripple is larger than the flying
  capacitance** and dominates the area.
- Even at 100 MHz the capacitors alone are about 0.36 mm², above the 0.25 mm²
  draft row, **before** switches, oscillator, drivers, clamp and routing.
  S7 = 0.50 mm² leaves about 0.14 mm² for those at 100 MHz and nothing at
  50 MHz. That headroom is an estimate.
- Enable-to-output (S4): charging C_out of about 0.6 nF to 4.5 V takes about
  2.7 nC, negligible against a 10 µs budget at tens of mA; S4 is not the
  binding row.
- The ripple row is the second lever: 200 mV ripple would halve C_out (to
  250 pF required at the minimum corner, 278 pF nominal) and bring total
  capacitor area at 100 MHz to
  **0.217 mm²**. Against the 0.25 mm² draft row that leaves only **0.033 mm²**
  for switches, oscillator, drivers, clamp and routing — about 4× less headroom
  than the **0.14 mm²** left under S7 = 0.50 mm² at 100 mV ripple — so relaxing
  ripple to 200 mV alone still leaves little margin inside 0.25 mm² once
  overhead is counted.

### 3.2 Pulsed bootstrap / charge-reservoir candidate

Source of the figures: the candidate topology and its 100 nC / ~65 nF /
`cap_mim_2f0` / ~6.7 V figures are from the 2026-11-25 comment on issue #1
(community suggestion, wafer.space Discord). The arithmetic below is re-derived.

An inverter drives the bottom plate of a cap; a diode from VDD feeds the top
plate; the top reaches about 2·VDD − V_d, and the stored charge is dumped into
the load. Charge delivered is Q = I · t, droop ΔV = Q / C. With the inherited
10 mA and an allowed 1.5 V droop:

| Pulse | Q | C = Q / 1.5 V | Area at 1.79 fF/µm² |
|---|---|---|---|
| 10 µs (inherited A3) | 100 nC | 66.7 nF | 37 mm² |
| 1 µs | 10 nC | 6.67 nF | 3.7 mm² |
| 100 ns | 1 nC | 0.67 nF | 0.37 mm² |

Reading:
- At the inherited 10 µs it is two orders of magnitude over S7. It cannot meet
  S3 as written, so it is **not a replacement for S3**.
- It is viable only if the fuse blows on a short, high-current pulse, and that
  duration is unsourced. At 100 ns the area (0.37 mm²) is comparable to the
  continuous pump and, with the same overhead, still exceeds 0.25 mm².
- Value as an experiment: stepped reservoir sizes bound the actual blow energy,
  which would replace A2/A3 in gf180-efuse-otp with a measurement. That is
  that repo's change.
- It is proposed, at most, as a separate stretch row once a blow-energy figure
  exists. It is not ratified here.

## 4. Device ceiling and stress arguments

For the 6 V process option, the foundry specifies 6 V DC between the
thick-oxide gate and any other FET terminal. Drain hot-carrier limits
depend on voltage, conduction time and direction. The manual treats periodic
gate overvoltage separately and requires lifetime and duty-cycle evidence.
This block takes no periodic-overvoltage credit. [GF180 chip operating
conditions, §§14.1.2–14.1.4](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_1.html)

For the selected circuit, measure each device's absolute Vgs, Vgd, Vgb and
Vds, and the signed drain–body and source–body junction differentials, across
startup, switching, no load, load steps, disable and every specified PVT
corner. Apply a 6.0 V project ceiling to these magnitudes, and enforce any
tighter applicable hot-carrier, oxide or junction limit, including forward
bias in the actual well connection. The 6.0 V ceiling is a conservative
screen. Junction ratings, polarity, terminal waveforms and compliance still
require evidence for the selected devices.

- S2/S8 limit VOUT relative to VSS. For the VOUT-to-ground reservoir they
  imply at most 5.5 V between plates while those bounds hold. A transistor
  connected to VOUT also has independently moving gate, source, drain and
  body potentials. Evaluate those differences directly.
- `nfet_10v0_asym` stays excluded: the PDK's own KLayout PCell fails the native
  deck (`CO.4`, `DF.6_MV`, `PL.4_MV`) at default settings. Using it needs its
  own decision record. Outputs above about 6 V are out of scope.
- A topology that meets the output by exceeding a rating is a failing result.

### First-order stress arguments for the candidate topologies

All figures use VDD = 3.63 V, the high corner; V_d ≈ 0.7 V is an assumed diode
or Vth drop, unsourced.

- **Cross-coupled (latched) doubler.** A flying plate initially at 3.63 V
  with its bottom plate at ground can approach 7.26 V to ground as the bottom
  plate rises to 3.63 V. The flying capacitor can retain ~3.63 V between
  plates in the same interval. A disconnected internal node may reach this
  peak while the VOUT limiter is still holding 5.5 V. Use the chosen switch
  and well connections to check every terminal differential, including the
  phase overlap and the first cycles after the load disappears. Verify the
  limiter's response at VOUT separately.
- **Dickson (diode-connected chain).** With a 0.7 V drop per stage, one
  stage gives about 5.2 V unloaded at 2.97 V input. Its loaded voltage must
  be simulated. A two-stage chain could approach 9.5 V unloaded at 3.63 V.
  An internal stage feeding a 5.5 V output through a forward-biased diode
  can be near 6.2 V to ground. Determine the actual Vds, gate and junction
  voltages from the selected circuit and check limiting or isolation for
  each internal stage.
- **Pulsed bootstrap.** The top plate can approach 2·3.63 − 0.7 ≈ 6.6 V to
  ground. At a bottom-plate potential of 3.63 V this corresponds to about
  3.0 V across that ideal flying cap. Apply S8 to VOUT and check the
  half-bridge, diode and other devices against S6 during charge, boost and
  load release.
- **Clocking: internal oscillator vs external clock.** A 3.3 V-only shuttle pad
  ring gives no spare pin guarantee, and a pump that needs an external clock
  moves a speed-critical signal across a pad. Proposal: internal oscillator is
  the default; an external clock input is optional and test-only. The oscillator
  frequency across PVT sets C_fly and C_out through §3.1, so the minimum
  frequency over corners (not typical) is the sizing frequency.

This record names these candidates and does **not** choose; selection is the
follow-on record with simulated evidence.

## 5. Open items that this record cannot verify

- The native KLayout array report in gf180-efuse-otp lists 27 foundry
  `EF.*` checks and zero violations on the drawn array. The report covers
  that layout only. Whether the foundry permits pump metal or a MIM
  reservoir over the fuse body remains open. The area budget takes no
  credit for that placement. [Native array DRC report](https://github.com/2AMLogic/gf180-efuse-otp/blob/fa9bcc4b104b6fa2eebc3d481856b1b0615c7090/layout/drc-array.native.report.json) · [eFuse issue #60](https://github.com/2AMLogic/gf180-efuse-otp/issues/60)
- The candidate schematic tests the 100 MHz assumption. Extracted clock and interconnect loading, startup, and the FSL allocation still require a routed circuit and the measured load sequence.
- The chosen devices' junction and drain constraints, actual body connections
  and transient terminal extrema remain to be verified under §4.
- MIM density is taken from the simulation model, not a measured wafer value;
  the model's own corner spread is ±10%.

### Candidate measurements and remaining acceptance tests

The 65 integrated ngspice 46 traces use five MOS process sections, three temperatures and 2.97/3.30/3.63 V. Slow and fast MOS track their resistor and BJT corners, and TT/FS/SF use typical passives. Each high-input hot and cold case exercises all three MIM corners. The 65 baseline cases cover 65 of the proposed 135 MOS/MIM/temperature/supply combinations. The other 70 combinations require verification. Separate passive-cross and transient-timestep controls are available. The 24 µs waveform ramps the load for 10 µs, holds 10 mA for 10 µs, then releases it. The following measurements refer to the schematic at commit `31635c5`. The same records are available in this revision. [65-case results](../sim/active-regulation/records/pvt.json) · [Timestep, supply-ramp and passive controls](../sim/active-regulation/records/controls.json) · [Load-edge and feedback controls](../sim/active-regulation/records/isolation.json) [65 traces](https://github.com/2AMLogic/gf180-charge-pump/blob/31635c530771b3f5dc070c3fc1cd1970fbb03a47/sim/active-regulation/records/pvt.json) · [Load-edge and isolation controls](https://github.com/2AMLogic/gf180-charge-pump/blob/31635c530771b3f5dc070c3fc1cd1970fbb03a47/sim/active-regulation/records/isolation.json)

| Review quantity | Result and scope |
|---|---|
| S2/S3/S5 | 4.69170–5.10574 V across the full 10 mA hold. Worst individual hold ripple was 36.57 mV on those 65 traces. An additional intact-loop passive-cross control (slow MOS, fast MIM/resistor/BJT, 125 °C, 2.97 V) lowers the observed loaded minimum to 4.61299 V. |
| Clock sizing | The slower of the two phases in each case ranged from 122.83 to 343.83 MHz. Each frequency is 20 divided by the measured elapsed time between crossings 20 cycles apart at full load. |
| S6/S8 | The 65-case maximum release and reservoir plate differential were 5.44194 V. Thick-oxide gate/body and drain/body excursions reached 5.74246 V. Thin drain/body reached 3.64875 V. The grid and negative-control breakdown below governs the S6 interpretation. |
| S7 | The placed M4/M5 capacitors occupy 0.442420 mm². Their native MIM DRC passes, while the full native deck finds five density markers on the unwired coupon. The design has 0.057580 mm² left for switches, control, wells, guard rings, power delivery, fill and routing. [Capacitor GDS and DRC](https://github.com/2AMLogic/gf180-charge-pump/tree/31635c530771b3f5dc070c3fc1cd1970fbb03a47/sim/active-regulation/records) |
| Input supply and efficiency | Loaded average VIN current reaches 68.979 mA. At the worst-efficiency corner, the settled VOUT extrema bracket the 10 mA power efficiency between 19.36% and 19.47%. At nominal the bracket is 34.96–35.16%. At enabled no load, maximum input current is 68.940 mA (250.25 mW input), including up to 131.535 mW in the shunt. |

Measure host supply power as the time average of `−VIN × I(VIN source)` and useful output power as the time average of `VOUT × Iload` over the same settled interval. Report startup peak current, average on-load current, enabled idle power, EN-low supply current and reverse leakage with VOUT precharged separately. A host supply and thermal allocation is needed before specifying numerical product limits for these quantities. The candidate values above are measurements to compare against that allocation.

For **Area-Eff**, audit the final routed core with pinned `klt economy`. Use the 500,000 µm² S7 budget and require bbox tightness 1.0. Report each dead margin, the largest empty regions and utilization. Identify the guard, matching, isolation and routing function of any proposed reserved space. The analog core needs a layout-derived utilization floor. On the capacitor-only GDS, utilization is 92.79% with zero edge margins, bbox tightness 1.0 and a largest connected empty region of 31,893.76 µm². Each MIM and its shielding and routing consume upper-metal area. Any increase in reservoir area to limit S8 transients also consumes S7 headroom. [MIM placement](../sim/active-regulation/records/capacitors.gds) · [Native MIM-B and full-deck coupon DRC](../sim/active-regulation/records/coupon-drc.json) · [KLT layout economy](../sim/active-regulation/records/coupon-economy.json)

For **statistical verification (T1 item 6)**, the reference, limiter, feedback ratio and PGOOD comparator introduce mismatch into S2, S8 and the 4.5 V indication. Run the pinned mismatch-enabled GF180D device models with independent seeds, save the seed list and report the joint fraction meeting those rows with a stated binomial confidence interval. Check the worst deterministic corners as well as nominal. Record PGOOD rising/falling thresholds, hysteresis and false assertions before a valid rail under ramp/load/release; PGOOD must be low while VOUT is below 4.5 V. A comparator implementation, offset distribution and host-approved transition tolerance are still needed. A deterministic PVT matrix supplies no mismatch yield.

#### Terminal stress and failure controls

These are peak magnitudes in volts from simultaneous waveforms over the complete 24 µs grid traces. The forward columns use the physical MOS polarity. Gate-field limits depend on the actual terminal pair and voltage class. Use the thin-oxide DC gate-to-any-terminal limit of 3.63 V and the 6 V process thick-oxide limit of 6.0 V. [GF180 device operating limits, §14.1.4](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_1.html#device-voltage-limits)

| MOS class (65 cases) | GS | GD | GB | DS | DB | SB | Forward DB | Forward SB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3.3 V | 3.21169 | 3.61669 | 3.21169 | 3.63013 | 3.64875 | 1.48056 | 0.16515 | 0.00010 |
| 6 V | 4.60831 | 4.69331 | 5.74246 | 5.44194 | 5.74246 | 3.63000 | 0.97831 | 0.02274 |

Fifty of the 65 baseline cases exceed a 3.3 V terminal-pair magnitude. The thin gate/drain reaches 3.61669 V, leaving 13.31 mV to the published 3.63 V maximum DC gate-pair screen. The 3.64875 V drain/body result is a junction quantity. Thin drain/source reaches 3.63013 V. Record actual well bias, injection current, accumulated exposure and the applicable time or duty allowance for each excursion. S6 remains open. The intact controls also give up to 3.29956 V thin GS/GB and 0.00057 V thin forward SB. The PNP has up to 0.83122 V emitter/base in the intact runs.

At FF/−40 °C/3.63 V, opening the output shunt drives the reservoir to 6.27646 V and the 6 V MOS gate/body and drain/body magnitudes to 6.38250 V. This negative control violates both S8 and the 6 V project screen. Report it alongside the operating circuit's worst cases. The older ideal-shunt topology also reached 5.945 V NMOS body-referenced and approximately 0.991 V forward junction on its shunted grid, then 6.370 V body-referenced with its shunt open under trapezoidal integration. That baseline uses different feedback and transistor waveforms. [Earlier 149-trace terminal record](../sim/clock-cap-screen/README.md#mos-terminal-stress-and-output-limiter)

For **electromigration and body current**, extract the actual current paths and measure each switching metal segment, via array, body tie and supply entry under load, release and worst-case inrush. Check directed or bidirectional current, temperature, duty and parallel via sharing against the applicable GF180 reliability limits at 125 °C. As an initial routing bound, carrying the 68.979 mA measured average through one unidirectional trunk at 125 °C requires at least 45.99 µm of 11 kÅ MetalTop at 1.5 mA/µm, or 102.96 µm on M1–M4 at 0.67 mA/µm. A transition limited to 0.18 mA per cut requires at least 384 equally sharing vias. These figures use the foundry limit directly. The actual branch currents, current sharing and additional margin must be checked on the routed design. Verify guard collection and allowed junction currents for any forward-biased well. Supply-current averages and terminal-voltage extrema alone leave these tests open. [GF180 electromigration rules](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_2.html)

## 6. Interface

| Pin | Direction | Description |
|---|---|---|
| VDD | in | 3.3 V supply, S1 |
| VSS | in | ground |
| EN | in | enable, 3.3 V logic; low means output off and pump stopped |
| CLK_EXT | in | optional external clock, test-only (§4); unused when internal oscillator runs |
| TRIM[1:0] | in | output trim/limit setting; the limit holds Vout ≤ 5.5 V (S8); lower settings are the stretch programmable range |
| PGOOD | out | high when Vout ≥ 4.5 V |
| VOUT | out | program supply to the host OTP block |

Load-side connection a host OTP block expects: VOUT is a supply rail feeding
the OTP block's own program path, which gates the current; the pump sees
pulsed loads (0 → 10 mA steps) and must stay within S2 and S6 on the step. When
EN is low, VOUT must not back-drive VDD.

## 7. Ratification

Rows S1–S9 are ratified on merge. Until then they are proposed targets.
Stretch rows are outside this decision.

Two independent reviewers, one EE and one market, review the same commit.
Neither reviewer may have authored the PR or the design. The operator then
approves that commit and `2am/ratification` must pass before merge. A new
commit requires both reviews and operator approval again.
