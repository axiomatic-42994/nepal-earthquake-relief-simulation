# Nepal Earthquake Relief Simulation (2015)

This repository contains the end-to-end data science and simulation pipeline for
analyzing humanitarian needs following the 2015 Nepal earthquake and simulating
the dispatch of relief vehicles through the damaged road network.

## ⚠️ Known repository defect: `lda_pipeline/` is not actually here

`lda_pipeline/` is recorded in git as a **submodule gitlink** pointing at commit
`403a711157a643be7ff407fa40dc2617fe7d29fa`, but the repository has **no
`.gitmodules` file**, so the submodule was never registered with a URL. The
directory is empty in every checkout, and git cannot recover it:

```
$ git submodule status
fatal: no submodule mapping found in .gitmodules for path 'lda_pipeline'

$ git submodule update --init lda_pipeline
fatal: No url found for submodule path 'lda_pipeline' in .gitmodules
```

Consequences, all of which affect the whole team:

- The NLP half of the project (Yashodeep's NMF pipeline) is **not represented in
  this repository at all**, which matters directly for the report's
  individual-contributions section.
- `alignment_results.json` and `topic_schema.json` are absent, so
  `sumo_simulation/scripts/compute_demand_proportions.py` cannot be run and the
  topic → class breakdown cannot be re-verified from source here.
- The pipeline is **not reproducible end to end from a clean checkout**. Only
  stages 2 onward can be run, from the committed
  `demand/real_demand_proportions.json`.

**To fix** (needs the URL of the NMF repository from Yashodeep):

```bash
git rm --cached lda_pipeline
git submodule add <url-of-nmf-repo> lda_pipeline
git -C lda_pipeline checkout 403a711157a643be7ff407fa40dc2617fe7d29fa
git add .gitmodules lda_pipeline
```

Vendoring the NMF outputs directly (committing `alignment_results.json` and
`topic_schema.json` into this repo) is the simpler alternative if the pipeline
does not need to be re-runnable here — but it should be done as its own commit,
attributed to Yashodeep, not folded into unrelated work.

## Repository Structure

- `lda_pipeline/` — (Authored by Yashodeep) The NMF topic-modeling pipeline that
  processes tweets into disaster-related themes and classes. **Currently empty —
  see the defect note above.**
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
Navigate to `lda_pipeline/` and follow its README to train the NMF model and
generate `alignment_results.json` and `topic_schema.json`.
**Blocked until the submodule defect above is resolved.**

### 2. Generate the Demand Proportions
```bash
cd sumo_simulation
python scripts/compute_demand_proportions.py
```
Reads the NMF confusion matrix and writes
`demand/real_demand_proportions.json`. **Also blocked on stage 1** — the
committed output file is what the rest of the pipeline currently runs on.

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
