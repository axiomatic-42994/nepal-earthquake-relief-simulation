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
sumo_simulation/
├── network/
│   ├── kathmandu.osm              # Raw OpenStreetMap export (Kathmandu valley)
│   └── kathmandu.net.xml          # SUMO network: 1,964 edges, 855 nodes
├── vehicles/
│   ├── vtypes.add.xml             # SUMO vehicle type definitions (ambulance, cargo_truck, first_responder)
│   └── topic_vehicle_map.json     # Mapping: NMF ground-truth classes → SUMO vehicle types
├── demand/
│   ├── real_demand_proportions.json    # NMF-derived dispatch proportions (the live interface input)
│   ├── relief_vehicles.rou.xml         # Generated relief vehicle trips (150: 97/28/25)
│   ├── relief_vehicles_routed.rou.xml  # Routed relief trips (via duarouter)
│   ├── background_routes.rou.xml       # Civilian background traffic, single-run (1,500 vehicles)
│   └── bg_routes_{42,101,202,303,404}.rou.xml  # Per-seed background traffic (1,200 vehicles each)
├── damage/
│   └── road_damage_events.json    # Timed earthquake damage events (7 full, 6 partial blockages)
├── scripts/
│   ├── compute_demand_proportions.py   # NMF alignment_results.json → dispatch proportions
│   ├── generate_demand.py              # Dispatch proportions → SUMO vehicle trip XML
│   ├── run_simulation.py               # Main TraCI loop (dynamic rerouting or static baseline)
│   ├── evaluate_results.py             # Parses tripinfo.xml → performance metrics
│   ├── verify_delivery_integrity.py    # Delivery-verified metrics (see "Reading the metrics" below)
│   ├── run_statistical_replication.py  # Runs N=5 seeds for statistical robustness
│   ├── run_all_windows.py              # Multi-window orchestration — DOES NOT RUN, see note inside
│   └── generate_visualizations.py      # Produces charts for report/slides
├── output/
│   ├── tripinfo_dynamic.xml       # Single unseeded run — dynamic rerouting mode
│   ├── tripinfo_static.xml        # Single unseeded run — static baseline mode
│   ├── tripinfo_{dynamic,static}_{seed}.xml  # The N=5 replication that produced the reported results
│   └── visualizations/            # Exported PNG charts
└── kathmandu_relief.sumocfg       # SUMO configuration file
```

Note: `demand/mock_lda_input.json` and `demand/lda_schema.json` appeared in an
earlier version of this listing. Neither exists any more — the mock interface was
replaced by `real_demand_proportions.json`, and the schema now lives in
`interface/demand_schema.md`.

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

Reads `output/tripinfo_dynamic.xml` and `output/tripinfo_static.xml` — the
**single unseeded run**, not the reported N=5 replication — computes fulfillment
rate, average delivery time and per-vehicle-type breakdown, and writes
`output/comparison_report.md` and `output/comparison_summary.json`.

### 5. Statistical Replication (5 seeds)

```bash
python scripts/run_statistical_replication.py
```

Re-runs both modes across seeds [42, 101, 202, 303, 404] with different
stochastic background traffic each time. Reports mean ± std for all metrics.
**This step produces the figures quoted in the report.**

### 6. Verify Delivery Integrity

```bash
python scripts/verify_delivery_integrity.py
```

Re-derives the metrics with abandoned missions excluded — see
"Reading the metrics" below. Reads committed output only; runs without SUMO.

### 7. Generate Visualizations

```bash
python scripts/generate_visualizations.py
```

Exports charts to `output/visualizations/`. Note that
`delivery_time_dist.png` is built from the **single unseeded run**, while
`replication_*.png` are built from the **N=5 seeded runs**; they are not two
views of the same experiment.

## Reading the metrics

**This was a real defect and it has been fixed** (commit `20c4784`). The history
matters, because older drafts of the report quote the pre-fix numbers.

When the TraCI controller abandons a vehicle it calls
`traci.vehicle.remove(...)`, and SUMO **still writes a `<tripinfo>` record** for
it, with `arrival` set to the removal time. The original `parse_tripinfo`
counted one tripinfo record as one delivery, so an abandoned mission was indexed
as a completed one — typically with `duration="1.00"`, which also cleared the
300s fulfilment threshold and pulled the mean duration down.

Measured on the committed N=5 output: **10 vehicles per dynamic run** are removed
this way, every one of them blocked by the same edge `1194719931`. Static mode
performs **zero** removals, so the bias only ever flattered dynamic mode.

`parse_tripinfo` now takes a `route_file` argument and drops any record whose
`arrivalLane` does not lie on its assigned route's final edge:

| Metric (N=5 mean)   | Pre-fix | Corrected (current) |
|---|---|---|
| Dynamic delivered   | 145.00 | 135.00 |
| Dynamic stranded    | 5.00   | 15.00  |
| Dynamic fulfilment  | 95.87% | 89.20% |
| Dynamic avg duration| 157.13s| 168.31s|
| Fulfilment gain     | +25.07pp | +18.40pp |
| Vehicles delivered vs static | +10.20 | +0.20 |

**Static-mode figures were never affected** — 70.80%, 240.33s, 87.27s and 15.20
stranded stand exactly as originally published, because no removals occur there.

Two caveats worth keeping in mind:
- The filter is only active when `route_file` is passed. `parse_tripinfo(path, n)`
  without it silently returns the old inflated counts (kept for backward
  compatibility). `run_statistical_replication.py`, `generate_visualizations.py`
  and `evaluate_results.py` all pass it.
- Run `scripts/verify_delivery_integrity.py` to see both columns side by side and
  to list the specific vehicles that were abandoned.

## Key Design Decisions

- **Fleet capacity**: Max 8 vehicles per type active simultaneously (24 total).
  Remaining dispatches are queued and released as vehicles complete trips.
- **Unreachable destinations**: If TraCI rerouting cannot find any path that
  avoids fully blocked edges, the vehicle is logged as UNDELIVERABLE and
  removed from the simulation. Note this is an *abandonment* policy: in static
  mode those same vehicles crawl through the 0.1 m/s rubble and do eventually
  arrive (durations 405–1625s on seed 42). Dynamic mode giving up on them is a
  modelling choice, not a physical impossibility — and see "Reading the metrics"
  for how it is currently mis-counted.
- **Non-binary damage**: Edges can be FULLY BLOCKED (speed → 0.1 m/s) or
  PARTIALLY BLOCKED (speed → 2.5 m/s) with different delay impacts. Only fully
  blocked edges trigger rerouting; partially blocked ones stay routable.
- **Scope decision (Part E)**: Final results use a single static aggregate
  demand distribution, not a 25-day loop. The dataset has no real per-day
  tweet timestamps. The multi-window orchestrator (`run_all_windows.py`) is
  retained as a design sketch but does not run and produces no reported results.

## Testing

```bash
python -m unittest discover -s ../tests -v     # from sumo_simulation/
python -m unittest discover -s tests -v        # from the repository root
```

69 tests covering the demand-conversion arithmetic, the interface schema
validator, the TraCI rerouting/fleet decision logic, the damage schedule's
invariants, and the phantom-arrival defect. They need only `numpy`; SUMO is not
required.
