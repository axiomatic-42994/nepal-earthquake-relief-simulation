# Nepal Earthquake 2015 — SUMO/TraCI Disaster Response Simulation

Dual-stage disaster response framework simulating relief vehicle dispatch
across the Kathmandu road network during the 2015 Nepal earthquake, using
SUMO microscopic traffic simulation controlled via TraCI.

## Prerequisites

| Dependency | Version Used | Notes |
|---|---|---|
| Python | 3.14.3 | 3.10+ should work |
| SUMO | 1.27.1 | Must set `SUMO_HOME` environment variable |
| numpy | 2.4.1 | |
| pandas | 2.3.3 | |
| matplotlib | 3.10.8 | |
| seaborn | 0.13.2 | |

TraCI and sumolib are bundled with SUMO (accessed via `SUMO_HOME/tools/`),
not installed separately via pip.

```bash
pip install -r requirements.txt
```

## Folder Structure

```
nepal_earthquake_sim/
├── network/
│   ├── kathmandu.osm              # Raw OpenStreetMap export (Kathmandu valley)
│   └── kathmandu.net.xml          # SUMO network converted via netconvert
├── vehicles/
│   ├── vtypes.add.xml             # SUMO vehicle type definitions (ambulance, cargo_truck, first_responder)
│   └── topic_vehicle_map.json     # Mapping: NLP topic categories → SUMO vehicle types
├── demand/
│   ├── mock_lda_input.json        # Placeholder NLP proportions (replaced by real data in Part F)
│   ├── lda_schema.json            # Schema definition for the NLP→SUMO interface
│   ├── relief_vehicles.rou.xml    # Generated relief vehicle trips
│   ├── relief_vehicles_routed.rou.xml  # Routed relief trips (via duarouter)
│   └── background_routes.rou.xml  # Stochastic civilian background traffic
├── damage/
│   └── road_damage_events.json    # Timed earthquake damage events (edge blockages)
├── scripts/
│   ├── generate_demand.py         # Converts NLP proportions → SUMO vehicle trip XML
│   ├── run_simulation.py          # Main TraCI simulation loop (dynamic rerouting or static baseline)
│   ├── evaluate_results.py        # Parses tripinfo.xml → performance metrics
│   ├── run_statistical_replication.py  # Runs N seeds for statistical robustness
│   ├── run_all_windows.py         # Multi-window orchestration (NOT used for final results — see note inside)
│   └── generate_visualizations.py # Produces charts for report/slides
├── output/
│   ├── tripinfo_dynamic.xml       # SUMO trip output — dynamic rerouting mode
│   ├── tripinfo_static.xml        # SUMO trip output — static baseline mode
│   └── visualizations/            # Exported PNG charts
└── kathmandu_relief.sumocfg       # SUMO configuration file
```

## How to Run (Step by Step)

### 1. Generate Demand (from NLP proportions)

```bash
python scripts/generate_demand.py \
    --demand-input demand/real_demand_proportions.json \
    --net network/kathmandu.net.xml \
    --output demand/relief_vehicles.rou.xml \
    --total-vehicles 150
```

This reads the topic proportions and generates SUMO `<trip>` elements with
randomised origin/destination edges.

### 2. Compute Baseline Routes

```bash
duarouter -n network/kathmandu.net.xml \
          -r demand/relief_vehicles.rou.xml \
          -o demand/relief_vehicles_routed.rou.xml \
          --ignore-errors true --no-warnings true
```

### 3. Run the Simulation

**Dynamic mode** (TraCI rerouting around earthquake debris):
```bash
python scripts/run_simulation.py --mode dynamic
```

**Static baseline** (no rerouting — vehicles follow pre-computed paths):
```bash
python scripts/run_simulation.py --mode static
```

Optional flags:
- `--gui` — launch `sumo-gui` instead of headless `sumo`
- `--seed 42` — set SUMO random seed
- `--output path/to/tripinfo.xml` — custom output path

### 4. Evaluate Results

```bash
python scripts/evaluate_results.py
```

Reads `output/tripinfo_dynamic.xml` and `output/tripinfo_static.xml`,
computes fulfillment rate, average delivery time, per-vehicle-type breakdown,
and outputs a comparison report.

### 5. Statistical Replication (5 seeds)

```bash
python scripts/run_statistical_replication.py
```

Re-runs both modes across seeds [42, 101, 202, 303, 404] with different
stochastic background traffic each time. Reports mean ± std for all metrics.

### 6. Generate Visualizations

```bash
python scripts/generate_visualizations.py
```

Exports charts to `output/visualizations/`.

## Key Design Decisions

- **Fleet capacity**: Max 8 vehicles per type active simultaneously (24 total).
  Remaining dispatches are queued and released as vehicles complete trips.
- **Unreachable destinations**: If TraCI rerouting cannot find any path that
  avoids fully blocked edges, the vehicle is logged as UNDELIVERABLE and
  removed from the simulation.
- **Non-binary damage**: Edges can be FULLY BLOCKED (speed → 0.1 m/s) or
  PARTIALLY BLOCKED (speed → 2.5 m/s) with different delay impacts.
- **Scope decision (Part E)**: Final results use a single static aggregate
  demand distribution, not a 25-day loop. The dataset has no real per-day
  tweet timestamps. The multi-window orchestrator (`run_all_windows.py`) is
  retained as a capability but does not produce any reported results.
