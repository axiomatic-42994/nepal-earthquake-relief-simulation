# Nepal Earthquake Relief Simulation (2015)

This repository contains the end-to-end data science and simulation pipeline for
analyzing humanitarian needs following the 2015 Nepal earthquake and simulating
the dispatch of relief vehicles through the damaged road network.

## Repository Structure

- `lda_pipeline/` — (Authored by Yashodeep) The NMF topic-modeling pipeline that
  processes tweets into disaster-related themes and classes, plus the selected
  model's outputs under `models/selected/` (`topic_schema.json`,
  `alignment_results.json`, `metadata.json`).
- `sumo_simulation/` — (Authored by Pratik) The SUMO/TraCI traffic simulation,
  dynamic pathfinding logic, and statistical evaluation scripts.
- `interface/` — The integration layer connecting the NLP output to the
  simulation input: the shared schema, the class → dispatch-category mapping,
  and the validator that gates one against the other.
- `tests/` — Unit tests for the demand conversion, the schema validator, and the
  TraCI rerouting/fleet decision logic.
- `reports/` — The final statistical summary report.

## Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.10+ | 3.13 and 3.14 both work |
| SUMO | 1.27.1 | Required for stages 1–4. `SUMO_HOME` must be set. |
| numpy, pandas, matplotlib, seaborn | see `sumo_simulation/requirements.txt` | pinned |

`traci` and `sumolib` ship with SUMO and are **not** pip-installable; they are
imported from `$SUMO_HOME/tools`.

```bash
pip install -r sumo_simulation/requirements.txt
```

Stages that need **no** SUMO install: the test suite,
`scripts/evaluate_results.py`, and `scripts/verify_delivery_integrity.py`. They
work from the committed simulation output.

## How to Run End-to-End

### 1. Run the NLP Pipeline
Navigate to `lda_pipeline/` and follow `INSTRUCTIONS.md` to train the NMF model
and regenerate `models/selected/{alignment_results,topic_schema,metadata}.json`.
The selected model's outputs are committed, so this stage only needs re-running
if the model itself changes.

### 2. Generate the Demand Proportions
```bash
cd sumo_simulation
python scripts/compute_demand_proportions.py
```
Reads `lda_pipeline/models/selected/alignment_results.json` and writes
`demand/real_demand_proportions.json`. Verified to reproduce the committed file
exactly: 2,882 / 844 / 752 documents → 0.6436 / 0.1885 / 0.1679.

Validate it against the interface contract:
```bash
python ../interface/validate_lda_output.py demand/real_demand_proportions.json
```

### 3. Generate the Simulation Demand
```bash
python scripts/generate_demand.py --demand-input demand/real_demand_proportions.json \
                                  --net network/kathmandu.net.xml \
                                  --output demand/relief_vehicles.rou.xml \
                                  --total-vehicles 150
duarouter -n network/kathmandu.net.xml -r demand/relief_vehicles.rou.xml \
          -o demand/relief_vehicles_routed.rou.xml \
          --ignore-errors true --no-warnings true
```

### 4. Run the Statistical Replication
```bash
python scripts/run_statistical_replication.py
```
The full N=5 seeded experiment (seeds 42/101/202/303/404) comparing dynamic
TraCI rerouting against the static baseline. **This is the stage that produces
the reported results.**

### 5. Check Delivery Integrity
```bash
python scripts/verify_delivery_integrity.py
```
Re-derives the metrics counting only vehicles that actually reached their
destination. Read this before quoting any dynamic-mode number — see
`sumo_simulation/README.md`, "Reading the metrics".

### 6. Generate Visualizations
```bash
python scripts/generate_visualizations.py
```
Charts are saved to `sumo_simulation/output/visualizations/`.

## Tests

```bash
python -m unittest discover -s tests -v
```
