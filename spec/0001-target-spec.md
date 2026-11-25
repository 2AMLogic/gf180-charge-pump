# 0001 — Target specification for the on-die program-supply charge pump

Status: proposed

Issue: #1. Classification: changes spec rows and bounds, so both the EE review
and the market review apply (CLAUDE.md, Ratification).

This record proposes the target-spec table row by row. It is analytic only:
no topology is chosen, nothing is simulated, and every number marked
*estimate* is a hand calculation that a later bench (#2) must confirm or
replace. Framing: a programming supply for on-die OTP cells.

## 1. Inputs inherited, and what is not known

The output and load rows inherit the program-supply assumptions A1-A3 of
[gf180-efuse-otp](https://github.com/2AMLogic/gf180-efuse-otp): 5.0 V ±10%,
≥ 10 mA, 10 µs. Those assumptions have **no PDK source**. This record treats
them as targets, not measured facts.

## 2. Proposed specification table

Every output-voltage row states its load current and corner.

| # | Parameter | Proposed target | Load / corner | Basis |
|---|---|---|---|---|
| S1 | Input supply | 2.97-3.63 V (3.3 V ±10%) | all | README draft |
| S2 | Output voltage | 4.5-5.5 V | I_load = 10 mA, all PVT corners (tt/ff/ss/fs/sf × −40/25/125 °C × VDD 2.97/3.30/3.63 V) | inherited A1; upper bound also set by §4 |
| S3 | Load current | ≥ 10 mA, continuous for ≥ 10 µs | at S2 voltage, worst corner | inherited A2/A3 |
| S4 | Enable to output in spec | ≤ 10 µs | I_load = 0 → 10 mA step after settle, worst corner | README draft; §3 shows reservoir charge is small against this |
| S5 | Output ripple | ≤ 100 mV p-p | I_load = 10 mA, worst corner | README draft; sets output capacitance (§3) |
| S6 | Device stress | no device above its rated Vds / Vgs / Vdb, any node, transients included | all corners, VDD = 3.63 V is the worst case | §4 |
| S7 | Core area (footprint including all capacitors) | **≤ 0.50 mm²** (draft: 0.25 mm²) | n/a | §3; **proposed change to a draft row** |
| S8 | No-load behaviour | output ≤ 5.5 V with EN high and no load | VDD = 3.63 V, hot and cold | §4; an unloaded doubler reaches 2·VDD = 7.26 V |
| S9 | PVT corners | as in S2 | n/a | README draft |

Stretch rows (programmable 4.0-5.5 V, ≥ 20 mA, ≤ 2 µs enable, ≤ 25 mV ripple,
≤ 0.10 mm²) are **not proposed for ratification here**. §3 shows ≥ 20 mA and
≤ 25 mV ripple each at least double the capacitance, so ≤ 0.10 mm² cannot
coexist with them. They stay in the README as named, unsized stretch items.

### Which row governs when load and area conflict

**The load row (S3) and ripple row (S5) govern; the area row moves.** The
sizing below shows 10 mA at ≤ 100 mV ripple cannot fit 0.25 mm² at any clock
rate this record considers reachable. S7 is therefore proposed at ≤ 0.50 mm²,
which §3 shows is reachable only at about 100 MHz or above. That clock rate is
an assumption about the 6 V devices at VDD = 2.97 V and is **not verified**.
The EE review decides whether the load row, the ripple row, or the area row
gives way. No row is claimed reachable beyond what §3 supports.

### What the pump commits to if A1-A3 move

- **A2 (current) rises to I′:** S2 stays 4.5 V minimum. The output-resistance
  budget scales as R_out ≤ 1.44 V / I′ (§3), and capacitance, hence area, scales
  about linearly with I′ at fixed clock rate. Up to 15 mA is a re-sizing within
  this record; above 15 mA needs a new record.
- **A3 (duration) shortens or lengthens:** the continuous pump is unchanged,
  because it is sized for continuous current. A duration short enough to make a
  pulsed reservoir viable is the separate candidate in §3.2, not a change to
  S3.
- **A1 (voltage) moves down:** covered by the trim/limit input (§6). **Above
  5.5 V:** out of scope (§4).
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

- `cap_mim_2f0` (M2/M3, M3/M4, M4/M5 and M5/M6 variants): `c_cox = 1.99e-3 F/m²`
  × `mim_corner_2p0ff`, i.e. **1.99 fF/µm²** typical. The corner multiplier is
  0.90 (ff) to 1.10 (ss), so the **minimum is 0.9 × 1.99 = 1.79 fF/µm²**. The
  sizing below uses 1.79 fF/µm² for area and requires C at the −10% corner.
  The fringe term (`c_capsw` = 2.38e-10 F/m, about 0.24 fF/µm of perimeter)
  is ignored; this makes the area slightly conservative for large plates.
- The device list header marks `cap_mim_2f0fF` "usable for Volt <= 6 V across
  capacitor". The MIM voltage in this record is at most about VDD (3.63 V), so
  this is respected; the cap's bottom-plate parasitic to substrate is a
  layout item for the topology record.
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

Split it evenly: 72 Ω slow-switching-limit (SSL) and 72 Ω for switch
resistance and parasitics. The even split is an assumption.

SSL output resistance of a doubler with total flying capacitance C_fly at
clock f_sw: R_SSL = 1 / (f_sw · C_fly). So C_fly = 1 / (f_sw · 72 Ω), then
divided by 0.9 for the low-capacitance corner.

Ripple: each phase delivers charge to the output, so
ΔV ≈ I / (2 · f_sw · C_out). With ΔV = 100 mV, I = 10 mA:
C_out = 0.05 / f_sw, also divided by 0.9.

| f_sw | C_fly (corner) | C_out (corner) | Capacitor area at 1.79 fF/µm² |
|---|---|---|---|
| 25 MHz | 617 pF | 2.22 nF | 1.43 mm² |
| 50 MHz | 309 pF | 1.11 nF | 0.71 mm² |
| 100 MHz | 154 pF | 0.56 nF | 0.36 mm² |

(Computed as (C_fly,typ + C_out,typ) / 1.79 fF/µm², which equals sizing the
typical values up by 1/0.9.)

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
  250 pF typical, 278 pF corner) and bring total capacitor area at 100 MHz to
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

Ceiling: `nfet_06v0` and `pfet_06v0`, treated here as 6.0 V on Vds, Vgs and Vdb
(inferred from the 6.0 V device class named in the PDK device list; per-terminal
Vds/Vgs/Vdb limits are **not** in the model files). The PDK's per-terminal
rating table is not reproduced in this record; the device-stress bench (#2) must
take the limits from the PDK documentation and check every node, transients
included. **This is an open item, not a verified rating.**

- The output upper bound S2/S8 (5.5 V) is set so no 6.0 V device on the output
  net exceeds its rating with 0.5 V of margin; margin policy for internal
  nodes is left to the topology record.
- `nfet_10v0_asym` stays excluded: the PDK's own KLayout PCell fails the native
  deck (`CO.4`, `DF.6_MV`, `PL.4_MV`) at default settings. Using it needs its
  own decision record. Outputs above about 6 V are out of scope.
- A topology that meets the output by exceeding a rating is a failing result.

### Per-candidate stress argument (analytic estimates, nothing simulated)

All figures use VDD = 3.63 V, the high corner; V_d ≈ 0.7 V is an assumed diode
or Vth drop, unsourced.

- **Cross-coupled (latched) doubler.** Unloaded, the output tends toward
  2·VDD = 7.26 V, above 6.0 V. It therefore needs an output limiter (S8) that
  holds Vout ≤ 5.5 V, for example by gating the clock. With the output held at
  ≤ 5.5 V, the cross-coupled pair's Vds and Vgs are bounded by Vout and stay
  under 6.0 V. The limiter's own response time against a load release is a
  transient stress item for #2.
- **Dickson (diode-connected chain).** Each stage adds about (Vclk − V_d). At
  the low corner (2.97 V) one stage gives about 2.97 + (2.97 − 0.7) = 5.2 V
  unloaded, so 10 mA load collapses it below 4.5 V; two stages are needed, and
  then the unloaded output is about 3.63 + 2 × (3.63 − 0.7) = 9.5 V, far above
  the ceiling. The last-stage node also reaches about Vout + V_d, i.e. up to
  about 6.2 V when Vout is at 5.5 V, which exceeds 6.0 V on Vdb or Vds. It
  needs both a limiter and a lower Vout cap, and it pays diode drops; the
  weakest candidate on stress and efficiency.
- **Pulsed bootstrap.** The top plate peaks at about 2·3.63 − 0.7 ≈ 6.6 V at
  the high corner (the issue comment gives ~6.7 V), above 6.0 V and above S8.
  It needs a clamp or limiter, and the device-stress bench (#2) must cover this
  transient. The half-bridge sees at most VDD. Diode reverse voltage is about
  6.6 − 3.63 ≈ 3 V.
- **Clocking: internal oscillator vs external clock.** A 3.3 V-only shuttle pad
  ring gives no spare pin guarantee, and a pump that needs an external clock
  moves a speed-critical signal across a pad. Proposal: internal oscillator is
  the default; an external clock input is optional and test-only. The oscillator
  frequency across PVT sets C_fly and C_out through §3.1, so the minimum
  frequency over corners (not typical) is the sizing frequency.

This record names these candidates and does **not** choose; selection is the
follow-on record with simulated evidence.

## 5. Open items that this record cannot verify

- Foundry `EF.*` rules for metal or MIM over the fuse body are not evaluated
  by the open KLayout deck (see gf180-efuse-otp#60). Whether a reservoir cap or
  any pump metal may sit over the OTP array is **unknown**. It is not assumed.
- The ≥ 100 MHz clock rate on 6 V devices at 2.97 V, and the 72 Ω switch
  budget, are assumptions for the topology record to test.
- The 6.0 V rated terminal voltages need to be taken from the PDK documents
  by #2.
- MIM density is taken from the simulation model, not a measured wafer value;
  the model's own corner spread is ±10%.

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

- This PR opens with `Status: proposed`.
- Rows proposed for ratification: S1-S9 as above. The stretch rows are not
  proposed.
- Reviews required: EE and market, distinct, neither the PR author nor the
  designer, each recorded against the head that carries the final status line.
  Reviewer files stay out of this repo.
