# Final Integration Report: NLP-Driven Simulation (Corrected)

> ### Revision note — the dynamic-mode figures below are the CORRECTED ones
>
> An earlier draft of this report quoted **95.87%** fulfillment, **157.13s**
> average duration and **5.00** stranded vehicles for dynamic mode, together with
> a claim that rerouting rescued *≈38 additional vehicles*. Those figures were
> inflated by a measurement defect: when the TraCI controller abandons an
> undeliverable vehicle it calls `traci.vehicle.remove()`, and SUMO still writes
> a `<tripinfo>` record for it — so an abandoned mission was counted as a
> completed delivery with a duration of about 1 second, which also cleared the
> 300s threshold and pulled the mean down. Static mode performs no removals, so
> the bias was entirely one-sided.
>
> Ten vehicles per dynamic run are affected, all blocked by the same edge
> `1194719931`. The fix (`parse_tripinfo`, commit `20c4784`) counts a record as a
> delivery only when its arrival lane lies on the vehicle's assigned final edge.
> Two independent derivations — one during the audit pass, one by the simulation
> author — produced identical corrected values.
>
> **All static-baseline figures were unaffected** and are unchanged from the
> original draft. If you are working from an older copy of this report or of the
> slides, the dynamic numbers there need replacing with the ones below.

This report presents the final statistical findings of the integrated Kathmandu earthquake relief simulation, driving SUMO TraCI stochastic dispatch directly from the document counts derived from the teammate's NMF topic modeling pipeline.

## 1. Demand Modeling (Path 3 Correction)
As verified in Part A and B, the actual document corpus heavily spikes towards injury reports rather than an even distribution. Using the true confusion matrix from `alignment_results.json`, we isolated 4,478 actionable documents from the 10,910 total corpus.

The dispatch fleet (150 vehicles) was dynamically generated using these exact proportions:
- **Ambulance (injured_or_dead_people)**: 64.36% (97 vehicles)
- **First Responder (missing_and_found_people)**: 18.85% (28 vehicles)
- **Cargo Truck (displaced / requests_or_needs)**: 16.79% (25 vehicles)

## 2. Statistical Replication (N=5 Seeds)
We ran the simulation across 5 random background traffic seeds (1,200 civilian passenger vehicles each). 

### Static Baseline (No Rerouting)
In the Static baseline, relief vehicles follow their initial pre-computed routes. When they encounter road sections that collapse into rubble at `t=300`, `t=1800`, or `t=3600`, they become stuck in the debris until the simulation ends.
- **Fulfillment Rate:** 70.80% (± 1.42%)
- **Average Delivery Duration:** 240.33s (± 24.46s)
- **Average Waiting Time:** 87.27s (± 24.03s)
- **Stranded Vehicles:** 15.20 (± 0.40)

### Dynamic Rerouting (TraCI Traversal)
Under Dynamic Rerouting, vehicles approaching heavily penalized debris edges trigger Dijkstra re-computation to find alternative, longer, but passable paths through the Kathmandu network.
- **Fulfillment Rate:** 89.20% (± 0.98%)
- **Average Delivery Duration:** 168.31s (± 3.32s)
- **Average Waiting Time:** 3.04s (± 3.11s)
- **Stranded / Abandoned Vehicles:** 15.00 (± 0.00)

## 3. Findings
The TraCI dynamic intervention demonstrates immense value under the true skewed demand distribution, though with a notable limitation regarding damage assessment.

- **+18.40% Delivery Success:** The fulfillment rate gain (deliveries under 300s) is significant, enabling roughly 28 more relief vehicles to reach their destinations on time compared to the static baseline.
- **72.02s Faster Turnaround:** Vehicles that avoid the debris complete their trips on average over a minute faster, dropping the average waiting time (traffic jam accumulation) from 87 seconds to near-zero (3.04s).
- **The Disjoint-Failure-Set Limitation:** Both dynamic and static modes fail to deliver ~15 vehicles, but they fail on different vehicles. The 10 that dynamic mode abandons share one structural property: edge `1194719931` is their **destination**, not merely a segment on the way to it. No reroute can avoid a vehicle's own destination, so `vehicle.remove()` here is not a routing failure that better pathfinding would have solved — the trip was unserviceable the moment that edge collapsed.

  Static mode records all 10 as arriving, but it is not a clean counter-example. The simulation runs with `--time-to-teleport 300`, and inspection of the raw `vaporized=` field shows **9 of those 10 arrivals are SUMO teleports** after the vehicle stalled for 301–1448s; only `cargo_truck_102` drives the final stretch unaided at 0.1 m/s. So the honest statement is not that patience beats rerouting — it is that **neither policy models a rubble-sited destination credibly**: dynamic abandons the mission, static teleports through the obstruction. The +18.40pp comparison is unaffected, since both arms are measured identically, but this caveat should accompany any claim about *why* the two modes fail differently.

## 4. Repository Consolidation
The project has now been unified into a single top-level `nepal-earthquake-relief-simulation` repository.
- `lda_pipeline/`: NMF training and evaluation scripts, plus the selected
  model's outputs (`models/selected/topic_schema.json`, `alignment_results.json`,
  `metadata.json`). Originally committed as a submodule gitlink with no
  `.gitmodules` entry, which left it empty in every clone; converted to tracked
  files in commit `b02e28e`.
- `sumo_simulation/`: XML networks, routing, and simulation runner.
- `interface/`: Connecting logic mapping classes to dispatch categories.
- `tests/`: Unit tests for the demand conversion, schema validator, and TraCI
  rerouting decision logic.
- `reports/`: This summary report.
