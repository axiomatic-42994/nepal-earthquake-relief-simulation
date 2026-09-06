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
- **Fulfillment Rate:** 95.87% (± 0.98%)
- **Average Delivery Duration:** 157.13s (± 3.09s)
- **Average Waiting Time:** 2.83s (± 2.90s)
- **Stranded Vehicles:** 5.00 (± 0.00)

## 3. Findings
The TraCI dynamic intervention demonstrates immense value under the true skewed demand distribution.
- **+25.07% Delivery Success:** The fulfillment rate gain is highly significant, rescuing roughly 38 total relief vehicles (approx. 25 per hour) from being permanently trapped in rubble.
- **83.20s Faster Turnaround:** Vehicles that avoid the debris complete their trips on average a minute and a half faster, dropping the average waiting time (traffic jam accumulation) from 87 seconds to near-zero (2.83s).
- **Deterministic Stranding (5.00):** Exactly 5 vehicles across all 5 random seeds remain permanently stranded. This is because their destinations (or departure points) are entirely enclosed by the rubble events, meaning the graph is mathematically disconnected and no reroute is physically possible.

## 4. Repository Consolidation
The project has now been unified into a single top-level `nepal-earthquake-relief-simulation` repository.
- `lda_pipeline/`: NLP scripts and JSON model outputs.
- `sumo_simulation/`: XML networks, routing, and simulation runner.
- `interface/`: Connecting logic mapping classes to dispatch categories.
- `reports/`: This summary report.
