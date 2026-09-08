# CHANGELOG — branch `audit/full-optimization-pass`

Full audit and optimization pass over the merged repository.
Base commit: `d3c93fb` ("Initial commit of verified integrated pipeline").
**Nothing here has been merged to `main`.**

---

## MERGE — `origin/main` merged in, both flagged items now RESOLVED

While this audit branch was being prepared, Pratik pushed three commits to `main`
that independently fix **both** of the items flagged below:

| Commit | Fixes |
|---|---|
| `b02e28e` | converts `lda_pipeline` from a broken gitlink to tracked files → **[FLAGGED-2] resolved** |
| `20c4784` | filters false deliveries out of `parse_tripinfo` → **[FLAGGED-1] resolved** |
| `d3a645c` | re-runs the N=5 simulation |

**Two independent derivations agreed exactly.** The audit pass and Pratik arrived
at the same corrected values from the same structural check (arrival lane vs the
route's final edge), with no coordination:

| Metric | Audit pass | Pratik's fix | Agree |
|---|---|---|---|
| Dynamic fulfillment | 89.20% (± 0.98%) | 89.20% (± 0.98%) | ✅ |
| Dynamic avg duration | 168.31s (± 3.32s) | 168.31s (± 3.32s) | ✅ |
| Dynamic avg waiting | 3.04s (± 3.11s) | 3.04s (± 3.11s) | ✅ |
| Dynamic stranded | 15.00 (± 0.00) | 15.00 (± 0.00) | ✅ |
| Fulfillment gain | +18.40pp | +18.40pp | ✅ |
| Delivery time saved | 72.02s | 72.02s | ✅ |

### The simulation is bit-for-bit deterministic

`d3a645c` is labelled "fresh simulation run", and the diff is only ~4 lines per
file. That is not a partial commit — it is the evidence. Re-running the whole
N=5 experiment on 2026-09-08 reproduced **every trip record byte-for-byte**; the
only changes were the generation timestamp and the TraCI port:

```diff
-<!-- generated on 2026-09-02T21:25:07.976008+05:45 by Eclipse SUMO sumo 1.27.1
+<!-- generated on 2026-09-08T16:45:38.154115+05:45 by Eclipse SUMO sumo 1.27.1
-        <remote-port value="57516"/>
+        <remote-port value="59472"/>
```

So all figures in this changelog, derived from the pre-`d3a645c` output, remain
valid against the post-`d3a645c` output.

### Merge resolution

One conflict: both branches added `sumo_simulation/scripts/verify_delivery_integrity.py`.
**Pratik's version was kept** — it is functionally complete (N=5 aggregation,
original-vs-corrected columns, static control, false-delivery listing) and is the
version his own commit references. The audit version added only CLI ergonomics
(`--seeds`, `--single-run`, `--json`) and was dropped rather than overwrite a
teammate's committed file.

`evaluate_results.py` and `reports/final_integration_report.md` auto-merged
cleanly, but the result was **semantically stale** — documents written during the
audit still described both defects as unfixed. Reconciled by hand:

- `README.md` — the `lda_pipeline` defect section removed; stages 1–2 unblocked.
- `reports/final_integration_report.md` — the audit's "unresolved" correction
  notice replaced with a revision note recording the pre-fix values, so anyone
  holding an older draft or slide deck knows what to replace. §4 corrected.
- `sumo_simulation/README.md` — "Reading the metrics" rewritten to describe the
  fixed state, keeping the history and adding the caveat below.
- `sumo_simulation/scripts/evaluate_results.py` — the audit's provenance header
  said the report's counts were inflated; now says they are filtered.

### Follow-ups introduced by the merge

- **The false-delivery filter is opt-in.** `parse_tripinfo(path, n)` without
  `route_file=` still returns the old inflated counts (deliberate backward
  compatibility). The three in-repo callers all pass it, but any new caller that
  forgets will silently reproduce the original defect. Worth making the
  parameter required once nothing depends on the old signature.
- **`false_deliveries` is computed but never returned** (`evaluate_results.py`
  line 91). Surfacing it in the returned dict would let the count appear in the
  generated report instead of only in `verify_delivery_integrity.py`.
- The audit's `tests/` suite passes unchanged against the merged tree (69 tests),
  including the four that pin the phantom-arrival counts in the raw XML.

---

## Verified after the merge — three previously-blocked checks now closed

`b02e28e` supplied the NMF artifacts the audit pass could not see. All three
checks that were left open are now done, against real source data.

### 1. Model identity — confirmed

`lda_pipeline/models/selected/metadata.json`:
`model_type: "sklearn_nmf"`, `k: 30`, `num_docs: 10910`, `vocab_size: 2251`,
`init: "nndsvda"`, `random_state: 42`. Matches the brief exactly (NMF, not LDA).

### 2. Topic → class breakdown — confirmed exactly, all 30 topics

The audit brief asked for this to be re-counted against the live
`topic_schema.json` rather than trusted. Done — every class and every topic id
matches:

| Class | topic_schema.json | Brief | Topic ids |
|---|---|---|---|
| sympathy_and_support | 15 | 15 | 0,2,3,4,5,6,9,12,13,14,17,22,23,25,28 |
| donation_and_volunteering | 5 | 5 | 1,16,19,26,29 |
| injured_or_dead_people | 2 | 2 | 7,21 |
| displaced_and_evacuations | 2 | 2 | 8,11 |
| caution_and_advice | 2 | 2 | 18,24 |
| missing_and_found_people | 2 | 2 | 20,27 |
| response_efforts | 1 | 1 | 10 |
| not_humanitarian | 1 | 1 | 15 |
| **Total** | **30** | **30** | |

The four zero-topic classes are confirmed absent from the schema entirely:
`requests_or_needs`, `infrastructure_and_utilities_damage`,
`other_relevant_information`, `personal_update`. **The corrected "15 topics" for
`sympathy_and_support` is right — the old "14" was indeed a documentation-only
error.**

### 3. Demand proportions — reproduced from the real confusion matrix

`compute_demand_proportions.py` (as hardened in [CHANGE-2]) run against the real
`alignment_results.json` reproduces the committed
`demand/real_demand_proportions.json` **exactly**:

```
total documents      : 10910      (committed: 10910)
actionable           : 4478       (committed: 4478)
non-actionable       : 6432       (committed: 6432)
raw counts           : {'ambulance': 2882, 'cargo_truck': 752, 'first_responder': 844}
proportions          : {'ambulance': 0.6436, 'cargo_truck': 0.1679, 'first_responder': 0.1885}
descoped (road_dmg)  : {}
EXACT MATCH: True
```

`descoped == {}` also confirms empirically what [CHANGE-2] could previously only
argue from the topic counts: the `road_damage_signal` path carries **zero**
documents, so closing that leak changed nothing about the published demand split.

### [NOT-DONE-1] Environment constraint — the simulations could not be re-run

This machine has **no SUMO installation** and no `seaborn`:

```
$ echo "SUMO_HOME=[$SUMO_HOME]"          -> SUMO_HOME=[]
$ Get-Command sumo                        -> sumo not on PATH
$ Get-ChildItem C:\,E:\ -Filter duarouter.exe -Recurse   -> (no results)
$ python -c "import seaborn"              -> ModuleNotFoundError: No module named 'seaborn'
$ python --version                        -> Python 3.13.13
```

So `generate_demand.py`, `run_simulation.py`, `run_statistical_replication.py`
and `generate_visualizations.py` **were not executed**. (`compute_demand_proportions.py`
was also blocked at the time, for the separate reason in [FLAGGED-2]; after the
merge it runs and reproduces the committed output exactly — see "Verified after
the merge" above.)

Pratik's `d3a645c` does re-run the full N=5 experiment on a machine with SUMO,
which independently confirms `run_simulation.py` and
`run_statistical_replication.py` still work — but that was run against **his**
copies of those scripts, before this branch's robustness edits. The edited
versions still need one end-to-end run.

Everything below was instead verified against the **committed raw simulation
output** (`output/tripinfo_*.xml`, `demand/*.rou.xml`, `network/kathmandu.net.xml`).
For confirming the published results this is arguably better evidence than a
re-run: it re-derives them from the exact artifacts the report was built on,
rather than from a fresh run that might differ. It is **not** a substitute for
end-to-end execution of the edited scripts, which still needs doing on a machine
with SUMO before this branch is merged.

---

## 🚩 FLAGGED — affects Section 1 "final verified results"

### [FLAGGED-1] Dynamic-mode metrics count abandoned missions as successful deliveries

**Status: RESOLVED in `20c4784` (Pratik), via option (c) below — the accounting
was fixed in `parse_tripinfo`, leaving the simulation logic untouched. The
analysis below is kept as the record of how the defect was found and quantified.**

**What is wrong.** `evaluate_results.py` treats every `<tripinfo>` record as a
completed delivery:

```python
trips = [t for t in root.findall('tripinfo') if ...]
completed = len(trips)
fulfilled = [t for t in trips if float(t.attrib['duration']) <= threshold_seconds]
```

That assumption breaks in dynamic mode. When the TraCI controller gives up on a
vehicle (`run_simulation.py`, the UNDELIVERABLE branch) it calls:

```python
traci.vehicle.remove(veh_id, traci.constants.REMOVE_PARKING)
```

**SUMO still writes a `<tripinfo>` record for a TraCI-removed vehicle**, with
`arrival` set to the removal time. So an abandoned mission is written out looking
like a successful one.

**Mechanism, verified.** All 10 removed vehicles per dynamic run share one
blocked edge, `1194719931`, on their route. `rerouteTraveltime` cannot route
around it, the post-reroute check fires, and the vehicle is deleted — normally
within 1 second of spawning, having covered only the depot edge:

```
UNDELIVERABLE vehicles -> present in tripinfo?  (tripinfo_dynamic_42.xml)
  ambulance_16   PRESENT  depart=921.00 arrival=922.00 duration=1.00 routeLength=123.40
  ambulance_20   PRESENT  depart=1151.00 arrival=1152.00 duration=1.00 routeLength=123.40
  ambulance_4    PRESENT  depart=247.00 arrival=300.00 duration=53.00 routeLength=816.37
  ... (10 of 10 PRESENT)
```

The damage is threefold and all in the same direction:
1. abandoned vehicles are counted as `completed`;
2. their ~1s duration clears the 300s threshold, so they count as **fulfilled**;
3. their ~1s duration and 0s waiting time pull both means down.

**The bias is one-sided.** Static mode performs **zero** removals
(`grep -c UNDELIVERABLE` over the static sections of `replication_run_real.log`
returns 0), so only the dynamic arm — the one whose superiority is being claimed —
is inflated.

**Worse: dynamic mode abandons vehicles that static mode delivers.** On seed 42
the two failure sets are completely disjoint. All 10 vehicles the dynamic
controller deletes complete successfully in static mode by crawling through the
0.1 m/s rubble:

```
id                   static dur  static len  static reached?   dyn dur  dyn len
ambulance_4              452.00     2670.32  True                53.00   816.37
ambulance_16             405.00     2129.92  True                 1.00   123.40
ambulance_20            1569.00     2129.92  True                 1.00   123.40
cargo_truck_102         1625.00     2255.08  True                 1.00   119.90
first_responder_131      874.00     2671.82  True                 1.00   124.90
   (10 of 10 reached their destination in static mode)
```

**How the corrected numbers were derived.** Not from the log — from a structural
property of the raw output that works identically for both arms:

> delivered ⇔ `edge_of(tripinfo.arrivalLane) == route.edges[-1]`

i.e. did the vehicle's recorded arrival lane sit on the last edge of the route it
was actually given in `relief_vehicles_routed.rou.xml`? This self-controls: in
static mode **100%** of tripinfo records pass, which is what you would expect if
the check itself were sound. Implemented in the new
`scripts/verify_delivery_integrity.py`.

**Corrected results (N=5):**

| Metric | Reported (Section 1) | Delivery-verified | Verdict |
|---|---|---|---|
| Static fulfillment | 70.80% (±1.42%) | 70.80% (±1.42%) | ✅ **stands** |
| Static avg duration | 240.33s (±24.46s) | 240.33s (±24.46s) | ✅ **stands** |
| Static avg wait | 87.27s (±24.03s) | 87.27s (±24.03s) | ✅ **stands** |
| Static stranded | 15.20 (±0.40) | 15.20 (±0.40) | ✅ **stands** |
| Dynamic fulfillment | 95.87% (±0.98%) | **89.20% (±0.98%)** | ⚠️ overstated |
| Dynamic avg duration | 157.13s (±3.09s) | **168.31s (±3.32s)** | ⚠️ overstated |
| Dynamic avg wait | 2.83s (±2.90s) | **3.04s (±3.11s)** | ⚠️ marginal |
| Dynamic stranded | 5.00 (±0.00) | **15.00 (±0.00)** | ❌ **wrong** |
| Fulfillment gain | +25.07% | **+18.40pp** | ⚠️ overstated |
| Delivery time saved | 83.20s | **72.02s** | ⚠️ overstated |
| "37.6 vehicles rescued (≈25/hr)" | +10.20 vehicles | **+0.20 vehicles** | ❌ **wrong** |

**What survives:** the qualitative conclusion holds strongly. Dynamic rerouting
still produces a large, consistent improvement in on-time fulfilment
(+18.4 percentage points) and delivery speed (72s faster), with a 96.5% waiting
time reduction. Every static-baseline figure is correct as published.

**What does not survive:** the "Deterministic Stranding (5.00)" finding and the
"≈38 vehicles rescued" claim. Under the delivery-verified count both modes
deliver ~135 of 150 vehicles; dynamic mode strands 15.00, static 15.20.

**Why it was not fixed here.** Changing the removal accounting changes every
reported dynamic number, and the simulations cannot be re-run on this machine to
regenerate them. The team's options:
- **(a)** report both columns with the caveat (cheapest, fully honest);
- **(b)** change the UNDELIVERABLE branch to leave the vehicle in the network so
  it is genuinely stranded, and re-run all 10 simulations;
- **(c)** keep the removal but filter phantom arrivals in `evaluate_results.py`,
  which reproduces the delivery-verified column above with no re-run at all.

Option (c) requires no SUMO and reproduces the corrected column exactly; it is
the cheapest correct fix if the team wants one set of numbers.

**Verified by:** `python scripts/verify_delivery_integrity.py`;
`python -m unittest tests.test_rerouting_logic.TestPhantomArrivalDefect`
(4 tests, all pass, including the static-mode zero-phantom control).

---

### [FLAGGED-2] `lda_pipeline/` is not in the repository

**Status: RESOLVED in `b02e28e` (Pratik) — the gitlink was replaced with 4,328
lines of tracked files, including `models/selected/topic_schema.json`,
`alignment_results.json` and `metadata.json`. This unblocked three verifications
that the audit pass had to leave open; their results are in the new
"Verified after the merge" section below.**

`lda_pipeline` is recorded as a **submodule gitlink** to commit
`403a711157a643be7ff407fa40dc2617fe7d29fa`, but there is **no `.gitmodules`
file**, no `.git/modules/lda_pipeline`, and the object is not present locally.
The directory is empty in every checkout:

```
$ git ls-tree HEAD lda_pipeline
160000 commit 403a711157a643be7ff407fa40dc2617fe7d29fa	lda_pipeline

$ git submodule status
fatal: no submodule mapping found in .gitmodules for path 'lda_pipeline'

$ git submodule update --init lda_pipeline
fatal: No url found for submodule path 'lda_pipeline' in .gitmodules
```

Consequences:
- The NMF pipeline (Yashodeep's individually-attributed work) is **not
  represented in this repository at all** — directly relevant to the report's
  required individual-contributions section.
- `alignment_results.json` and `topic_schema.json` are absent, so
  `compute_demand_proportions.py` cannot run, and **the topic → class breakdown
  in the brief could not be re-verified against `topic_schema.json`** as the
  audit instructions asked. The mapping *was* cross-checked against the two
  copies that do exist in this repo, which agree with each other and with the
  brief (see [CHANGE-7]).
- The pipeline is not reproducible end-to-end from a clean checkout.

Not fixable from inside this repo — it needs the NMF repository URL from
Yashodeep. Recovery instructions added to the root `README.md`.

---

## ✅ CONFIRMED — Section 1 facts re-verified against raw data

All re-derived from committed artifacts, not from any prior summary.

| Claim | Result | Evidence |
|---|---|---|
| Network: 1,964 edges / 855 nodes | ✅ exact | counted non-`function` edges and non-internal junctions in `kathmandu.net.xml` |
| Fleet: 150 vehicles = 97 / 28 / 25 | ✅ exact | `grep -o 'type="..."' relief_vehicles.rou.xml \| sort \| uniq -c` |
| Proportions 0.6436 / 0.1885 / 0.1679 | ✅ exact | 2882/4478, 844/4478, 752/4478; sum = 1.0000 |
| Corpus 10,910 = 4,478 + 6,432 | ✅ exact | arithmetic in `real_demand_proportions.json` `_meta` |
| Static: 70.80% ±1.42, 240.33s ±24.46, 87.27s ±24.03, 15.20 ±0.40 | ✅ **all exact to 4 dp** | `parse_tripinfo` over the 5 committed `tripinfo_static_*.xml` |
| Dynamic: 95.87% ±0.98, 157.13s ±3.09, 2.83s ±2.90, 5.00 ±0.00 | ✅ reproduces exactly (but see [FLAGGED-1] for what it means) | same, over `tripinfo_dynamic_*.xml` |
| Gains: +25.07%, 83.20s, 96.76%, 37.6 vehicles | ✅ reproduces exactly | computed from the above |
| Dynamic stranded is deterministic, not a bug | ✅ confirmed deterministic — and now explained: the same 10 vehicles are blocked by the same edge `1194719931` every seed | `verify_delivery_integrity.py` |
| 5 seeds, ~1,200 background vehicles each, genuinely distinct | ✅ 1,200 exactly per seed | `grep -c "<vehicle " bg_routes_*.rou.xml` |
| Damage: 2 severity levels, non-binary | ✅ 7 fully blocked, 6 partially blocked, disjoint sets | `road_damage_events.json` + new tests |
| vTypes: 3, ambulance emergency+bluelight | ✅ confirmed | `vtypes.add.xml` |
| No placeholder labels remain | ✅ clean | grep for `medical_aid\|food_shelter\|search_rescue\|medical_help\|terrorism_or_other_violence` across all `.py/.md/.json/.xml` returned only the English word "shelter" in a prose description |
| The doc-only "14 topics" error | ✅ already fixed — only "15/30 topics" appears | grep |

The N=5 per-seed figures also match the archived
`output/replication_run_real.log` line for line (e.g. `[Seed 303] Static -
Fulfillment: 68.0%, Avg Duration: 286.7s`).

**Standard deviations are population σ (`np.std`, ddof=0), not sample σ.** With
N=5 the sample σ would be larger (e.g. static fulfillment ±1.59 rather than
±1.42). Not changed — it would alter published numbers — but the report should
say which is meant.

---

## Changes made

### [CHANGE-1] `interface/validate_lda_output.py` — hardened the schema gate

The audit brief asked for the validator to be tested with deliberately broken
input rather than read. It was, and it had **four real defects**:

| Input | Before | After |
|---|---|---|
| `{"ambulance":1.5,"cargo_truck":-0.3,"first_responder":-0.2}` | **exit 0 — ACCEPTED** (sums to 1.0) | rejected: out of `[0,1]` |
| string values `"0.6436"` | `TypeError` traceback | rejected cleanly |
| `"dispatch_proportions": ["a"]` | `AttributeError` traceback | rejected cleanly |
| `"dispatch_proportions": null` | `AttributeError` traceback | rejected cleanly |
| `{"ambulance": 1.0}` alone | accepted (would send all 150 vehicles to one category) | rejected: missing required categories |

The negative-proportion hole was the dangerous one: `-0.3` reaches
`generate_demand.py` as `round(150 * -0.3) = -45`, which `max(1, ...)` silently
turns into a single vehicle.

Also added: top-level type check, empty-dict check, `bool` rejection (`True`
would otherwise pass as `1.0`), and a `require_all_categories` opt-out.

**Verified:** 13-case adversarial battery, all malformed inputs rejected with a
single `FAILED:` line and no tracebacks; the real
`real_demand_proportions.json` still passes with exit 0. 19 unit tests in
`tests/test_schema_validator.py`.

### [CHANGE-2] `scripts/compute_demand_proportions.py` — closed a latent schema-breaking leak

`infrastructure_and_utilities_damage` maps to `road_damage_signal`, and the
original aggregation treated **anything not `'no_dispatch'`** as actionable:

```python
dispatch_cat = mapping.get(pred_class, 'no_dispatch')
if dispatch_cat == 'no_dispatch': no_dispatch_count += count
else: category_counts[dispatch_cat] = ...        # road_damage_signal lands here
```

Any non-zero count for that class would have emitted `"road_damage_signal"` into
`dispatch_proportions` — a category no SUMO vType implements — producing a file
that fails schema validation and a fleet split against a phantom category. It is
currently 0 only because that class has 0 topics assigned.

Fixed by routing descoped categories to their own bucket, excluded from
`dispatch_proportions` but still counted in the corpus total so the denominator
stays honest. **This does not resurrect the descoped integration** — it is
counted and loudly reported, never dispatched.

Also: `mapping.get(cls, 'no_dispatch')` silently discarded any unmapped class,
shrinking the actionable pool with no warning; that now raises. Added an
actionable `FileNotFoundError` message pointing at the `lda_pipeline` problem,
a `confusion_matrix`-missing check, and UTF-8 encoding on both file handles.

**Verified:** cannot be run (no `alignment_results.json`, see [FLAGGED-2]), so
verified by unit test instead — a reconstructed confusion matrix carrying the
published class counts reproduces `real_demand_proportions.json` exactly
(proportions, raw counts, and all three `_meta` totals). 19 tests in
`tests/test_demand_conversion.py`.

### [CHANGE-3] `scripts/run_simulation.py` — robustness, no behavioural change

- `resolve_sumo_binary()` replaces `os.environ['SUMO_HOME']` + hardcoded `.exe`.
  Was a bare `KeyError` when unset and Windows-only; now a clear message and
  cross-platform.
- `traci` import failure now explains that traci ships with SUMO, not pip.
- Route-file splitting used `routes_file.split(',')[1]` and
  `[p for p in ... if 'relief' in p][0]`. The second is a live trap: the
  repository directory is itself called `nepal-earthquake-**relief**-simulation`,
  so `'relief' in p` matches **every** path and the code silently depended on
  the relief file happening to be listed first. Both now match on
  `os.path.basename` and raise a clear error if the expected file is absent.
- `step % int(900 / step_length)` divided by zero for `step_length > 900`; now
  `max(1, ...)`.
- End-of-run summary now reports abandoned missions and any dispatch requests
  left in the queue, instead of leaving both silent.
- Removed an unused `running = traci.vehicle.getIDCount()`.
- Added a prominent in-code warning at the UNDELIVERABLE branch documenting
  [FLAGGED-1], so the defect cannot be re-derived unknowingly.

**Verified:** identical decision logic — the two inline predicates were extracted
verbatim (see [CHANGE-4]) and unit-tested. Cannot be executed without SUMO.

### [CHANGE-4] `scripts/run_simulation.py` — extracted pure decision predicates

`route_is_blocked()`, `is_due()` and `has_fleet_capacity()` were lifted verbatim
out of the TraCI loop so the control logic is testable without a running SUMO.
The call sites now read:

```python
if route_is_blocked(current_route, route_index, active_blocked_edges):
...
if is_due(req, sim_time):
    if has_fleet_capacity(req['type'], active_dispatch_counts, MAX_FLEET):
```

Behaviour is unchanged — same expressions, same operands. `tests/test_rerouting_logic.py`
covers 31 cases including the "every fleet vehicle simultaneously busy" edge case
named in the improvement mandate (capacity is per-type, so a saturated ambulance
fleet correctly does not block a cargo truck).

### [CHANGE-5] `scripts/verify_delivery_integrity.py` — new

Delivery-verified evaluation tool implementing the check described in
[FLAGGED-1]. Reads committed output only, never rewrites published results,
needs no SUMO. Prints the as-reported and delivery-verified columns side by side
so the gap is visible rather than argued.

**Verified:** its "as reported" column reproduces every Section 1 figure exactly,
which cross-validates it against the existing `evaluate_results.py`.

### [CHANGE-6] `scripts/evaluate_results.py` — provenance header on the generated report

`output/comparison_report.md` showed 68.7% / 94.7%, 22 stranded, 248.0s / 161.6s —
figures that flatly contradict the reported 70.80% / 95.87%. Nothing labelled it.
This is exactly the "two sources disagree" hazard the brief warns about.

Both are correct; they are **different experiments**. The report is a single
unseeded run against `background_routes.rou.xml` (**1,500** background vehicles);
the reported results are the N=5 replication (**1,200** per seed). The generator
template now emits a provenance block saying so, and pointing at [FLAGGED-1].

**Verified:** regenerated `comparison_report.md` and `comparison_summary.json`.
`git diff` on the JSON is **empty — byte-identical to the committed file**, which
proves the edit changed no computation. The `.md` shows 19 insertions, 0
deletions: pure header, no number touched.

### [CHANGE-7] Cross-file mapping consistency now enforced by test

The class → dispatch mapping exists in three places
(`interface/dispatch_category_mapping.json`,
`compute_demand_proportions.CLASS_TO_DISPATCH`,
`vehicles/topic_vehicle_map.json`) with no guard against drift. Tests now assert
they agree, that all 12 canonical classes are covered, that the validator's
allow-list equals the vType ids actually declared in `vtypes.add.xml`, and that
the topic-id assignments match the verified breakdown (T7/T21 → ambulance,
T20/T27 → first_responder, T8/T11 → cargo_truck, `requests_or_needs` → none).

All three sources currently agree, and agree with the audit brief.

### [CHANGE-8] `scripts/run_all_windows.py` — stopped it failing destructively

Documented as "retained as a capability", but it does not run, and one of its
failure modes is destructive. Verified broken in 5 ways, including:

> `run_window()` does `shutil.copy(routes_routed, 'demand/relief_vehicles_routed.rou.xml')`
> — **overwriting the exact file that reproduces every published result.**

It also calls `generate_demand.py --lda-input/--topic-map` (arguments that no
longer exist), calls `parse_tripinfo(path)` with one argument (it now needs two),
reads a `mock_lda_input.json` that is not in the repository, and hardcodes
`duarouter.exe`.

`main()` now aborts with the full checklist before touching any file. The
`except Exception: print(...)` that would have emitted a CSV looking complete
while silently missing windows now records the failure in the CSV and re-raises.

**Verified:** `python run_all_windows.py --run` exits 2 with the checklist and
touches nothing.

### [CHANGE-9] `scripts/generate_demand.py` — robustness, no behavioural change

- `actual_total` was computed and never used. Per-category rounding is
  independent, so the realised fleet need not equal `--total-vehicles`; it
  happens to land on exactly 150 here (97+25+28), but a different distribution
  would silently dispatch the wrong number. Now warns explicitly.
- Guarded the empty-`vehicles` case before `vehicles[0]` / `vehicles[-1]`.
- Clear error when `sumolib` cannot be imported.
- Docstring said proportions come from `topic_schema.json`; they come from
  `alignment_results.json`. Corrected.
- Documented that `find_destination_edges(n=30)` returns **28**, not 30
  (`max(1, n // 4)` per quadrant × 4). Confirmed empirically: the committed route
  file uses exactly 28 distinct destinations. Left as-is so published runs stay
  reproducible.

### [CHANGE-10] Documentation corrected

- **Root `README.md`** — rewritten: the `lda_pipeline` defect and its fix, honest
  prerequisites, which stages need SUMO and which do not, the validation step,
  the delivery-integrity step, tests.
- **`sumo_simulation/README.md`** — the folder listing named
  `demand/mock_lda_input.json` and `demand/lda_schema.json`; **neither exists**.
  Listing corrected and expanded, root renamed from `nepal_earthquake_sim/` to
  `sumo_simulation/`. Added a "Reading the metrics" section carrying the
  [FLAGGED-1] table, a note that `delivery_time_dist.png` is built from the
  single unseeded run while `replication_*.png` come from the N=5 runs, and the
  observation that UNDELIVERABLE is an abandonment *policy* rather than a
  physical impossibility.
- **`reports/final_integration_report.md`** — prominent correction notice at the
  top. **No published number altered**; the notice states which claims stand
  (all static figures), which are overstated, and which do not survive. §4's
  claim that `lda_pipeline/` holds NLP scripts corrected.

### [CHANGE-11] `tests/` — new, 69 tests

| File | Tests | Covers |
|---|---|---|
| `test_schema_validator.py` | 19 | the adversarial battery, placeholder-label rejection, validator/vType contract |
| `test_demand_conversion.py` | 19 | confusion-matrix aggregation, reproduction of the published proportions, descoped-category leak, cross-file mapping consistency, apportionment |
| `test_rerouting_logic.py` | 31 | reroute predicate, fleet admission, SUMO_HOME handling, damage-schedule invariants, phantom-arrival defect |

No SUMO required (`traci` is stubbed at import); only `numpy`.

```
$ python -m unittest discover -s tests
Ran 69 tests in 2.803s
OK
```

Two tests are worth calling out as guards rather than coverage:
- `test_every_damaged_edge_exists_in_the_network` — a typo in
  `road_damage_events.json` would raise `TraCIException` inside a bare
  `except ... : pass`, so the blockage would simply never happen and the
  simulation would silently model less damage than the report claims. All 13
  edges verified present.
- `test_static_runs_contain_no_phantom_arrivals` — the control that makes the
  [FLAGGED-1] measurement trustworthy.

---

## Deliberately NOT changed

| # | Finding | Why left alone |
|---|---|---|
| 1 | The UNDELIVERABLE removal logic itself | Changing it changes every reported dynamic number, and the simulations cannot be re-run here. Team decision — [FLAGGED-1]. |
| 2 | `find_destination_edges(n=30)` returning 28 | Real off-by-design, but changing it changes the destination set and therefore every published result. Documented instead. |
| 3 | Population σ instead of sample σ | Would alter every published ± figure. Flagged for the report to state which is meant. |
| 4 | `road_damage_signal` integration | Explicitly out of bounds, and correctly so — there is no real data behind it. |
| 5 | Any NMF/LDA modelling logic | Teammate's individually-attributed work, and absent from the repo anyway. |
| 6 | Weak topic-model alignment (Macro F1 0.0808) | A disclosed property of the NMF result, not a bug. |
| 7 | Committed PNG visualizations | `seaborn` is not installed, so they cannot be regenerated; regenerating would also rewrite committed artifacts. The single-run vs N=5 mismatch is documented instead. |
| 8 | The `evaluate_results.py` fulfilment denominator | `fulfillment_rate = fulfilled / 150` counts never-dispatched requests as unfulfilled alongside rubble-stranded ones (see [NEW-LIMIT-2]). Defensible as "requests not served in time", but conflates two causes. Left for the team. |

---

## New limitations discovered

**[NEW-LIMIT-1] Dynamic mode's abandonment policy can be worse than doing nothing.**
On seed 42 all 10 vehicles dynamic mode abandons are delivered successfully by
static mode. The controller treats "no reroute avoids the rubble" as "destination
unreachable", but a fully blocked edge is 0.1 m/s, not impassable — vehicles can
and do crawl through in 405–1625s. This is a genuine finding about the *policy*,
independent of the accounting defect, and it is arguably the more interesting
result: naive rerouting can destroy deliveries that patience would have completed.

**[NEW-LIMIT-2] Fleet saturation and rubble-stranding are conflated.**
The final heartbeat of the static seed-404 run reads `Queued: 3` — three dispatch
requests never departed at all, because the 8-per-type fleet cap never freed up.
They are counted in `uncompleted_or_stranded` alongside vehicles genuinely stuck
in debris. Static mode is affected more than dynamic (slower trips → slower queue
drain), so this slightly widens the measured gap for a reason unrelated to
rerouting.

**[NEW-LIMIT-3] Eight vehicles depart after t=5100.**
Departures are spread across the full 0–5400s window (max 5375.3s) while the
simulation ends at 5400s, so the last few structurally cannot complete. Affects
both arms similarly, but it puts a ceiling on the achievable fulfillment rate
that is an artifact of the demand-generation window, not of traffic conditions.

**[NEW-LIMIT-4] Depot/destination selection filters on `passenger` permission only.**
`find_depot_edges` and `find_destination_edges` test `e.allows('passenger')`, but
the fleet is `truck` and `emergency` vClass. Verified benign for the published
run — all 3 depots and all 28 destinations permit passenger, truck **and**
emergency — but a different network or seed could select an edge the fleet cannot
legally use. Latent, not active.

**[NEW-LIMIT-5] The `while` loop can abandon a non-empty dispatch queue.**
`while traci.simulation.getMinExpectedNumber() > 0` exits when no vehicles remain
in the network, even with requests still queued. Masked here because background
traffic runs the whole horizon, but it is a real dependency of the relief
pipeline on the background traffic file.

**[NEW-LIMIT-6] `run_statistical_replication.py` invokes bare `"python"`.**
It shells out with `subprocess.run(["python", ...])`, which picks up whatever is
first on `PATH` rather than the interpreter running the script — a venv mismatch
would run the child simulations against different package versions. Not changed
(`sys.executable` is the fix) because it would need a re-run to verify.

---

## Verification summary

| What | Command | Result |
|---|---|---|
| Section 1 final results | `python verify_delivery_integrity.py` | all 12 headline figures reproduce exactly |
| Test suite | `python -m unittest discover -s tests` | **69 tests, OK** |
| Schema validator, real file | `python interface/validate_lda_output.py sumo_simulation/demand/real_demand_proportions.json` | `SUCCESS`, exit 0 |
| Schema validator, malformed | 13-case battery | all rejected, no tracebacks |
| `evaluate_results.py` unchanged | regenerate + `git diff` | `comparison_summary.json` **byte-identical** |
| All Python compiles | `python -m py_compile scripts/*.py interface/*.py` | OK |
| Placeholder labels | grep across all source/doc/data | none found |
| `run_all_windows.py` guard | `python run_all_windows.py --run` | exits 2, touches nothing |

**Not verified:** anything requiring SUMO — `generate_demand.py`,
`run_simulation.py`, `run_statistical_replication.py`, `generate_visualizations.py`
were **not executed** ([NOT-DONE-1]). Their edits are robustness and
documentation only, plus one verbatim predicate extraction covered by unit tests,
but they have not been run end-to-end. **This should be done on a machine with
SUMO before merging.**
