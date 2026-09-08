# Final Integration Report: NLP-Driven Simulation (Corrected)

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
- **The Disjoint-Failure-Set Limitation:** Both dynamic and static modes fail to deliver ~15 vehicles, but they do so differently. When the TraCI rerouting logic detects a completely blocked destination, it correctly identifies that no alternative path exists and calls `vehicle.remove()` to abandon the mission. However, it fails to distinguish between "impassable rubble" and "slow but passable" degradation. In the static baseline, some of these same vehicles do eventually reach their destinations by slowly crawling through (and teleporting out of) the rubble over 15-25 minutes. Thus, dynamic mode trades higher overall efficiency for a strict, brittle abandonment policy when a corridor is choked.

## 4. Repository Consolidation
The project has now been unified into a single top-level `nepal-earthquake-relief-simulation` repository.
- `lda_pipeline/`: NLP scripts and JSON model outputs.
- `sumo_simulation/`: XML networks, routing, and simulation runner.
- `interface/`: Connecting logic mapping classes to dispatch categories.
- `reports/`: This summary report.
