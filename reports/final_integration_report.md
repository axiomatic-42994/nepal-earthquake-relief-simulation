# Final Integration Report: NLP-Driven Simulation (Corrected)

> ## ⚠️ CORRECTION NOTICE — added by the audit pass, unresolved
>
> **Every number in this report reproduces exactly from the committed simulation
> output.** They were re-derived from the raw `output/tripinfo_*_{seed}.xml`
> files and match to four decimal places. Nothing below is fabricated.
>
> **But three of the dynamic-mode claims do not mean what the report says they
> mean,** because of a measurement defect in `run_simulation.py`. When the TraCI
> controller abandons an undeliverable vehicle it calls `traci.vehicle.remove()`,
> and SUMO still writes a `<tripinfo>` record for that vehicle — so the abandoned
> mission is counted as a *completed delivery*, with a duration of about 1 second,
> which also clears the 300s fulfilment threshold and pulls the mean duration
> down. Static mode performs **no** removals, so the bias is entirely one-sided.
>
> Measured on the committed N=5 output: 10 vehicles per dynamic run are removed
> this way, all of them blocked by the same edge `1194719931`. In static mode
> those same 10 vehicles crawl through the 0.1 m/s rubble and genuinely arrive.
>
> Counting only vehicles whose recorded arrival lane lies on their route's final
> edge (`scripts/verify_delivery_integrity.py`):
>
> | Claim in §2/§3 below | As reported | Delivery-verified |
> |---|---|---|
> | Dynamic fulfillment rate | 95.87% (± 0.98%) | **89.20% (± 0.98%)** |
> | Dynamic avg delivery duration | 157.13s (± 3.09s) | **168.31s (± 3.32s)** |
> | Dynamic stranded vehicles | 5.00 (± 0.00) | **15.00 (± 0.00)** |
> | Fulfillment gain | +25.07% | **+18.40pp** |
> | Delivery time saved | 83.20s | **72.02s** |
> | "≈38 vehicles rescued (~25/hour)" | +10.20 vehicles | **+0.20 vehicles** |
>
> **All static-baseline figures in this report stand unchanged** — 70.80%,
> 240.33s, 87.27s, 15.20 stranded are all correct as printed.
>
> The qualitative finding survives: dynamic rerouting still delivers a large,
> statistically consistent improvement in on-time fulfilment (+18.4 percentage
> points) and delivery speed (72s faster). What does **not** survive is §3's
> "Deterministic Stranding (5.00)" paragraph and the claim that rerouting rescues
> ~38 extra vehicles — under the delivery-verified count both modes deliver ~135
> of 150, and the ~10 vehicles dynamic mode "saves" are an artifact.
>
> The simulation logic has deliberately **not** been changed, so the published
> runs stay reproducible. Deciding whether to re-run with corrected accounting,
> or to report both columns with this caveat, is a call for the team — see
> `CHANGELOG.md`, entry **[FLAGGED-1]**.

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
- `lda_pipeline/`: **Empty in every checkout.** Recorded as a submodule gitlink
  (`403a711`) with no `.gitmodules` entry, so git has no URL to fetch it from and
  `git submodule update --init` fails. The NLP scripts and JSON model outputs are
  not in this repository. See the root `README.md` for the fix.
- `sumo_simulation/`: XML networks, routing, and simulation runner.
- `interface/`: Connecting logic mapping classes to dispatch categories.
- `tests/`: Unit tests for the demand conversion, schema validator, and TraCI
  rerouting decision logic.
- `reports/`: This summary report.
