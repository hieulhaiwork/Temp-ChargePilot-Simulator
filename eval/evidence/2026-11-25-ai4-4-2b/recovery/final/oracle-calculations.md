# Gate 4 final remediation oracles

## G4-F01 — Time and energy

The old candidate accepted a revised deadline at T+7:30 and departed at T+8. With one available AC connector, booking A's departure is also B's plug-in. The baseline handoff occurs at A's original deadline T+15. B arrives at T+1, so its plug wait goes from 14 minutes to 7 minutes. B can charge for 5 baseline minutes or 12 patched minutes through T+20. Both cars draw 11 kW output and store 98% of that energy.

| Quantity | Baseline calculation | Reviewed candidate with T+7:30 patch |
|---|---:|---:|
| A battery kWh through T+20 | 11 × 0.98 × 15 / 60 = 2.695000 | 11 × 0.98 × 8 / 60 = 1.437333 |
| B battery kWh through T+20 | 11 × 0.98 × 5 / 60 = 0.898333 | 11 × 0.98 × 12 / 60 = 2.156000 |
| A original SLA | False | False |
| A revised SLA | — | False |

Each target needs 60.13 × (0.80 − 0.20) = 36.078 battery kWh. B stays in progress at T+20 and its original SLA is censored. The final candidate rejects the explicit T+7:30 input before running both branches. The positive oracle moves the physics grid origin to 12:00:30.123, takes a snapshot at T after two minutes and accepts T+7 in a different UTC offset. Moving the requested instant to a wall-clock minute or adding a microsecond makes it invalid. The target-only oracle retains an original T+7:30 deadline and the existing T+8 physical release.

## G4-F02 — Metric populations

In the regression fixture, baseline observed waits are A=10 and B=50. Mean is 30 and nearest-rank p90 is 50. Patched has A=15 and B waiting at cutoff. Mean and p90 are both 15. The observed sample changes from {A,B} to {A} for plug and charge wait. Their four deltas are null with `non_comparable_sample`. Both vehicles remain in the arrived denominator, making the service and charged coverage changes from 2/2 to 1/2 comparable. Charger output changes from 8 to 5 kWh and cost from 4,000 to 2,800 VND, giving deltas of −3 kWh and −1,200 VND.

Separate projections hold the denominator count fixed while swapping exactly one member in each of AC and DC. They exercise all three original SLA rates, both coverage rates and all four wait statistics. Keeping the same members yields signed differences. Empty/empty yields `missing_data`; unequal membership, including empty/nonempty, yields `non_comparable_sample`. The real connector-outage probe exercises the empty/nonempty case with identical arrived membership. Existing safety probes and a safe truncated-branch fixture verify full comparison suppression when the window or safety requirement fails.

## G4-F03 — Mixed AC/DC power and TOU

The fixture runs from 19:56 to 20:04 station time. The configured synthetic TOU price is 3,500 VND/grid kWh for the first four minutes and 2,000 for the last four. Grid-to-output efficiency is 0.95 and output-to-battery efficiency is 0.98. For interval length `m` with AC + DC actual output `P`, output kWh is `P × m / 60`, stored kWh is `0.98 × output kWh`, grid input is `output kWh / 0.95` and cost is `grid input kWh × interval price`. The two peak metrics are the maximum interval `P` and `P / 0.95`.

B0 starts with 22/78 kW AC/DC output budgets. For source limit `g`, each budget is multiplied by `min(1, 0.95 × g / 100)` and actual output is bounded by the equipment and each EV. In the 2 AC / 2 DC cases, every EV stays below the DC taper threshold and has ample remaining energy. The fixed budgets split equally within each zone. Each original deadline is T+8 with 36.078 battery kWh required per EV. All vehicles miss their original commitment, giving 0/4 overall and 0/2 per zone for the four-EV fixtures, and 0/2 overall and 0/1 per zone for the two-EV fixtures. Each asserted safety counter is zero.

- **Binding supply.** 40 kW grid gives AC/DC output 8.36/29.64 kW. An 80 kW site premise gives 16.72/59.28 kW for eight minutes. Each EV receives half its zone's output.
- **Equipment and acceptance.** Set site input from 106 to a hypothetical 140 kW. There is one AC vehicle (11 kW) and one DC vehicle. DC output is 60 kW with a single 60 kW connector, 25 kW with a 25 kW cabinet, 25 kW with a 25 kW physical zone cap and matching feasible B0 budget, or 16 kW with a vehicle acceptance cap of 16. The higher supply changes none of these outputs.
- **Announced decrease, increase and cabinet-only limit.** The four two-minute source regimes are 50 → 30 → 100 → 100 kW in baseline and 80 → 30 → 80 → 80 in patched. The cabinet-only event at T+6 clips DC output to 12 kW in both branches. AC output continues as 20.9 or 16.72 kW respectively. At the drop from 50 to 30 kW, the emergency factor is `(30 × 0.95) / (50 × 0.95) = 0.6`. For each DC port, the existing binary64 expression `18.525 × 0.6 × 1000 = 11114.999999999998` floors to 11114. The planned 11.115 kW differs by less than the 0.01 kW deadband, so actual DC output is 22.228 kW in that block. From 80 to 30 the factor is 0.375 and each DC port holds 11.115 kW.
- **Event effective at T.** With a known 30 kW source limit at T, the first block must run at `min(runtime override, 30)` or `min(site patch, 30)`. The 100 kW announced regime at T+4 replaces the captured starting regime and the 80 kW site cap still applies on patched. The probe checks the power-limit event reaches the control loop once per branch at each boundary. On the reviewed candidate an override of 50 masked the 30 kW event in baseline and produced 9.5 output kWh instead of 8.233333.

| Case | Output kWh | Stored kWh | Grid kWh | Peak output kW | Peak grid kW | TOU cost VND |
|---|---:|---:|---:|---:|---:|---:|
| Binding supply, baseline | 5.066667 | 4.965333 | 5.333333 | 38 | 40 | 14,666.67 |
| Binding supply, patched | 10.133333 | 9.930667 | 10.666667 | 76 | 80 | 29,333.33 |
| Connector, both | 9.466667 | 9.277333 | 9.964912 | 71 | 74.736842 | 27,403.51 |
| Cabinet or zone fixture, both | 4.800000 | 4.704000 | 5.052632 | 36 | 37.894737 | 13,894.74 |
| Vehicle cap, both | 3.600000 | 3.528000 | 3.789474 | 27 | 28.421053 | 10,421.05 |
| Future events, baseline | 6.796600 | 6.660668 | 7.154316 | 95 | 100 | 18,308.53 |
| Future events, patched | 6.974000 | 6.834520 | 7.341053 | 76 | 80 | 20,182.11 |
| Event at T, 20 kW override baseline | 7.600000 | 7.448000 | 8.000000 | 95 | 100 | 18,000.00 |
| Event at T, 50 kW override baseline | 8.233333 | 8.068667 | 8.666667 | 95 | 100 | 20,333.33 |
| Event at T, patched (both override fixtures) | 6.966667 | 6.827333 | 7.333333 | 76 | 80 | 17,666.67 |

[Reviewed-candidate replay](final-fail-before.stdout.txt) · [Final candidate oracles](gate/g4-oracles.stdout.txt)
