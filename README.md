# Nepal Earthquake Relief Simulation (2015)

This repository contains the full end-to-end data science and simulation pipeline for analyzing humanitarian needs following the 2015 Nepal earthquake and simulating the dispatch of relief vehicles through the damaged road network.

## Repository Structure

- `lda_pipeline/`: (Authored by Yashodeep) Contains the NLP topic modeling pipeline (NMF) that processes tweets to identify disaster-related themes and classes.
- `sumo_simulation/`: (Authored by you) Contains the SUMO/TraCI traffic simulation, dynamic pathfinding logic, and statistical evaluation scripts.
- `interface/`: The integration layer connecting the NLP output to the simulation input, defining the shared schema and mapping rules.
- `reports/`: Contains the final statistical summary report and generated visualizations.

## How to Run End-to-End

### 1. Run the NLP Pipeline
Navigate to `lda_pipeline/` and follow its README to train the NMF model and generate `alignment_results.json` and `topic_schema.json`.

### 2. Generate the Demand Proportions
The simulation consumes the NLP output to generate stochastic vehicle demand.
```bash
cd sumo_simulation
python scripts/compute_demand_proportions.py
```
*Note: This generates `demand/real_demand_proportions.json` based on the document counts in the `lda_pipeline` output.*

### 3. Generate the Simulation Demand
Convert the proportions into actual vehicle routes:
```bash
python scripts/generate_demand.py --demand-input demand/real_demand_proportions.json --net network/kathmandu.net.xml --output demand/relief_vehicles.rou.xml
```

### 4. Run the Statistical Replication
Execute the full N=5 seeded experiment comparing Dynamic TraCI rerouting against the Static baseline:
```bash
python scripts/run_statistical_replication.py
```

### 5. Generate Visualizations
Once the simulation completes, generate the final charts:
```bash
python scripts/generate_visualizations.py
```
Visualizations are saved to `sumo_simulation/output/visualizations/`.
