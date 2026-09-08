# Methodology — Dual-Stage Disaster Response Framework

**Drafting aid, not report copy.** Every figure below was re-derived from the
committed artifacts during the audit pass on branch
`audit/full-optimization-pass`, including the NMF outputs under
`lda_pipeline/models/selected/`. Dynamic-mode figures are the **corrected**
ones — see §5 and `CHANGELOG.md` entry **[FLAGGED-1]** for what changed and why.

---

## 1. System overview

The framework couples two stages that are usually studied separately:

1. **Need classification.** A topic model over crisis tweets from the 2015 Nepal
   earthquake assigns each document to a humanitarian need class.
2. **Dispatch and routing.** The aggregate class distribution parameterises a
   microscopic traffic simulation of Kathmandu in which relief vehicles are
   dispatched and — in the treatment condition — dynamically rerouted around
   earthquake damage.

The two halves meet at a single narrow contract: a JSON document giving the
proportion of relief demand attributable to each dispatchable vehicle type.
Keeping the interface this thin is deliberate — the simulation never sees a
tweet, and the topic model never sees a road.

```
CrisisNLP corpus ──► NMF (k=30) ──► class assignment ──► document counts
                                                              │
                                    interface/demand_schema.md │  (validated)
                                                              ▼
                                            real_demand_proportions.json
                                                              │
                                                              ▼
                              generate_demand.py ──► duarouter ──► SUMO/TraCI
                                                                       │
                                                          ┌────────────┴────────────┐
                                                     static baseline        dynamic rerouting
```

---

## 2. Stage 1 — Need classification

**Model.** Non-negative Matrix Factorisation, k = 30 topics
(`sklearn_nmf_k30`). The project's working name is "LDA pipeline"; the selected
model is NMF. Reports should say NMF.

**Corpus.** CrisisNLP / CrisisBench humanitarian tweets for the 2015 Nepal
earthquake: **10,910 documents**.

**Label space.** 12 canonical `mapped_ground_truth_class` values. Only **8**
receive any of the 30 topics; `requests_or_needs`,
`infrastructure_and_utilities_damage`, `other_relevant_information` and
`personal_update` receive none.

**Topic → class distribution**, verified topic-by-topic against
`lda_pipeline/models/selected/topic_schema.json`:

| Class | Topics | Topic ids |
|---|---|---|
| `sympathy_and_support` | 15 | 0, 2, 3, 4, 5, 6, 9, 12, 13, 14, 17, 22, 23, 25, 28 |
| `donation_and_volunteering` | 5 | 1, 16, 19, 26, 29 |
| `injured_or_dead_people` | 2 | 7, 21 |
| `displaced_and_evacuations` | 2 | 8, 11 |
| `caution_and_advice` | 2 | 18, 24 |
| `missing_and_found_people` | 2 | 20, 27 |
| `response_efforts` | 1 | 10 |
| `not_humanitarian` | 1 | 15 |
| **Total** | **30** | |

Model identity confirmed from `metadata.json`: `sklearn_nmf`, k = 30,
`num_docs` = 10,910, vocabulary 2,251, `init = nndsvda`, `random_state = 42`.

**Alignment quality.** Macro F1 ≈ 0.0808, accuracy ≈ 13.3%. This is a disclosed
limitation of the NMF result, not a defect to be corrected: unsupervised topics
are not obliged to align to a pre-existing label taxonomy, and reporting the weak
alignment honestly is more informative than tuning until it looks better.

---

## 3. The interface contract

`interface/demand_schema.md` fixes the exchange format;
`interface/validate_lda_output.py` enforces it and is the only gate between the
two halves. It rejects unknown categories, non-numeric or out-of-range
proportions, partial category sets, and any file whose proportions do not sum to
1.0 within 0.01. It was tested during the audit against a 13-case battery of
deliberately malformed inputs; all were rejected with a single diagnostic line
and no tracebacks.

**Class → dispatch category mapping** (`interface/dispatch_category_mapping.json`):

| Class | Dispatch category | Rationale |
|---|---|---|
| `injured_or_dead_people` | `ambulance` | casualty reports — emergency response |
| `missing_and_found_people` | `first_responder` | search and reunification |
| `displaced_and_evacuations` | `cargo_truck` | evacuation and shelter logistics |
| `requests_or_needs` | `cargo_truck` | supply requests — **0 topics, contributes nothing** |
| `infrastructure_and_utilities_damage` | `road_damage_signal` | **descoped, see §7** |
| all remaining 7 classes | `no_dispatch` | not actionable as a vehicle dispatch |

`response_efforts` is deliberately `no_dispatch` despite sounding actionable: the
representative tweet for its single topic (T10) is sentiment, not coordination
content. `sympathy_and_support` carries 15 of the 30 topics and dominates raw
counts, which is why the demand model is **document-weighted rather than
topic-weighted** — weighting by topics would let sympathy content swamp genuine
need signal.

### Demand derivation

Demand is computed from the alignment confusion matrix by summing predicted
document counts per class (`compute_demand_proportions.py`), mapping to dispatch
categories, discarding non-actionable classes, and renormalising:

| Category | Documents | Share | Vehicles (of 150) |
|---|---|---|---|
| ambulance | 2,882 | 64.36% | 97 |
| first_responder | 844 | 18.85% | 28 |
| cargo_truck | 752 | 16.79% | 25 |
| **Actionable total** | **4,478** | 100% | **150** |
| Non-actionable | 6,432 | — | — |
| **Corpus** | **10,910** | | |

All arithmetic verified (2882+752+844 = 4478; 4478+6432 = 10910; shares sum to
1.0000; the committed route file contains exactly 97/28/25 trips). Vehicle counts
come from `max(1, round(150 × proportion))` applied per category — which is not
guaranteed to sum to the requested total, though it does here.

---

## 4. Stage 2 — Traffic simulation

**Network.** Kathmandu, extracted from OpenStreetMap and converted with
`netconvert`: **1,964 edges and 855 nodes** (both counted directly from
`kathmandu.net.xml`, excluding SUMO-internal geometry).

**Vehicle types** (`vtypes.add.xml`):

| Type | vClass | Bluelight | Max speed | Notes |
|---|---|---|---|---|
| `ambulance` | `emergency` | yes | 33.33 m/s | may use emergency lanes, ignore red lights |
| `first_responder` | `emergency` | yes | 38.89 m/s | lighter, higher acceleration |
| `cargo_truck` | `truck` | no | 22.22 m/s | ordinary traffic rules |

**Damage model.** Three timed events at t = 300s, 1800s and 3600s, derived
deterministically (seed 2015) from the 50 highest-throughput edges by
`lanes × length`. Damage is **not binary**:

- **Fully blocked** (7 edges): max speed → 0.1 m/s, travel-time penalty 100,000.
  Passable in principle, but at ~0.36 km/h.
- **Partially blocked** (6 edges): max speed → 2.5 m/s, travel time set to
  `length / 2.5`.

Only fully blocked edges trigger rerouting; partially blocked edges stay
routable. All 13 edges were verified to exist in the network — a typo there would
be swallowed by the exception handler around `setMaxSpeed` and the blockage would
simply never occur.

**Fleet model.** At most 8 vehicles of each type may be active simultaneously.
Requests beyond that are held in a departure-time-ordered queue and released as
capacity frees. The cap is per type, so a saturated ambulance fleet does not
block cargo trucks.

**Background traffic.** ~1,200 stochastic civilian passenger vehicles per seed,
generated with SUMO's `randomTrips.py`, distinct per seed (verified: 1,200
`<vehicle>` elements in each `bg_routes_{seed}.rou.xml`).

### Experimental design

Two conditions over a 5,400s (1.5h) horizon, N = 5 seeds (42, 101, 202, 303, 404):

- **Static baseline.** Damage occurs; vehicles follow their `duarouter`
  pre-computed routes without adaptation.
- **Dynamic rerouting.** Identical damage schedule. Each step, any relief vehicle
  whose remaining route crosses a fully blocked edge triggers
  `rerouteTraveltime`. If the recomputed route still crosses one, the vehicle is
  declared UNDELIVERABLE and removed.

Both arms share the same demand file, the same routed paths, the same damage
schedule and the same background traffic per seed, so the only manipulated
variable is the rerouting policy. This is the design's main strength.

### Metrics

- **Fulfillment rate** — trips completing within a 300s operational threshold, as
  a share of all 150 dispatched requests.
- **Average delivery duration**, **average stopped waiting time** — means over
  completed trips.
- **Stranded vehicles** — dispatched requests with no completed trip.

Reported as mean ± standard deviation across the 5 seeds. The committed figures
use **population** σ (`numpy.std`, ddof=0); sample σ would be larger. State which
is meant.

---

## 5. Results

**Static baseline (N=5), verified exactly against the raw tripinfo output:**

| Metric | Value |
|---|---|
| Fulfillment rate | 70.80% (± 1.42%) |
| Average delivery duration | 240.33s (± 24.46s) |
| Average waiting time | 87.27s (± 24.03s) |
| Stranded vehicles | 15.20 (± 0.40) |

**Dynamic rerouting (N=5).** Quote the right-hand column — it is what the
pipeline now produces:

| Metric | Pre-fix (do not quote) | Current |
|---|---|---|
| Fulfillment rate | 95.87% (± 0.98%) | **89.20% (± 0.98%)** |
| Average delivery duration | 157.13s (± 3.09s) | **168.31s (± 3.32s)** |
| Average waiting time | 2.83s (± 2.90s) | **3.04s (± 3.11s)** |
| Stranded vehicles | 5.00 (± 0.00) | **15.00 (± 0.00)** |
| Fulfillment gain over static | +25.07pp | **+18.40pp** |

The columns differ because `traci.vehicle.remove()` still causes SUMO to emit a
`<tripinfo>` record, so an abandoned mission was indexed as a completed one —
typically with `duration = 1.00s`, which also cleared the 300s threshold. Static
mode performs no removals, so the bias was one-sided. `parse_tripinfo` now counts
a record only when its arrival lane lies on the final edge of the vehicle's
assigned route. Two independent derivations produced identical corrected values.
Full account in `CHANGELOG.md` **[FLAGGED-1]**; reproduce with
`scripts/verify_delivery_integrity.py`.

**What the study supports.** Dynamic rerouting produces a large and consistent
improvement in on-time delivery (+18.4 percentage points) and delivery speed
(72s faster, a 30% reduction), and very nearly eliminates queueing delay (87.27s
→ 3.04s, −96.5%). The effect is stable across all five seeds.

**What it does not support.** The claim that rerouting rescues ~38 additional
vehicles from being trapped, which appeared in pre-fix drafts. Under the
delivery-verified count both conditions deliver ~135 of 150; the apparent rescue
was an artifact of the removal accounting.

**A genuine limitation worth reporting.** All 10 vehicles the dynamic controller
abandons share one property: edge `1194719931` is their **destination**, not just
a via-edge. No reroute can avoid a vehicle's own destination, so abandonment is
structurally guaranteed for them rather than a routing failure.

Static mode records all 10 as arriving — but `--time-to-teleport 300` is active,
and the raw `vaporized=` field shows **9 of the 10 were teleported by SUMO** after
being stuck 301–1448s. Only `cargo_truck_102` drove the final stretch unaided.

So neither arm handles a rubble-sited destination honestly: dynamic abandons it,
static teleports through it. This does not affect the +18.40pp comparison, which
treats both arms identically, but it does mean the study cannot claim that
rerouting destroys deliveries patience would have completed.

---

## 6. Reproducibility

| Artifact | Command | Needs SUMO? |
|---|---|---|
| Demand proportions | `scripts/compute_demand_proportions.py` | no (needs the NMF output) |
| Schema validation | `interface/validate_lda_output.py <file>` | no |
| Route generation | `scripts/generate_demand.py` + `duarouter` | yes |
| N=5 replication | `scripts/run_statistical_replication.py` | yes |
| Metrics | `scripts/evaluate_results.py` | no |
| Delivery-verified metrics | `scripts/verify_delivery_integrity.py` | no |
| Unit tests (69) | `python -m unittest discover -s tests` | no |

Dependency versions are pinned in `sumo_simulation/requirements.txt`; SUMO 1.27.1
was used for the committed runs.

---

## 7. Limitations

**Disclosed by design:**

1. **No temporal demand curve.** The corpus has no usable timestamp field, so
   demand is a single static aggregate rather than a 25-day profile. The
   multi-window orchestrator exists as a design sketch but produced no reported
   result and does not currently run.
2. **Infrastructure damage → road closure was not integrated.**
   `infrastructure_and_utilities_damage` has zero topics assigned, so there is no
   real signal behind `road_damage_signal`. Damage is instead scripted from
   network topology. Synthesising documents for this class would have
   manufactured the result rather than finding it.
3. **Weak topic–class alignment** (Macro F1 ≈ 0.0808). A property of the NMF
   solution, disclosed rather than tuned away.

**Found during the audit:**

4. **Delivery accounting was wrong until commit `20c4784`.** Abandoned missions
   were counted as completed deliveries because SUMO writes a `<tripinfo>`
   record for TraCI-removed vehicles. Fixed, but any draft or slide deck
   produced before that commit carries the inflated dynamic-mode figures
   (95.87% / 157.13s / 5.00 stranded) and needs updating.
5. **Fleet saturation and rubble-stranding are conflated** in the stranded count.
   Three static-mode requests on seed 404 never departed at all because the fleet
   cap never freed up; they are counted alongside vehicles genuinely stuck.
6. **Departure window meets the horizon.** Departures spread to t = 5375s against
   a 5400s end time, so the last few trips structurally cannot complete —
   a ceiling on achievable fulfillment unrelated to traffic conditions.
7. **Single network, single damage schedule, single city.** Effect sizes are
   specific to this topology and this scripted damage; the 5 seeds vary only
   background traffic, not damage placement. Generalisation would need damage
   randomisation across seeds.
