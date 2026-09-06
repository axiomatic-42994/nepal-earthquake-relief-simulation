# Interface Contract: NLP Demand Schema

This document defines the strict schema that the SUMO TraCI simulation expects from the NLP analysis output. The NLP pipeline must produce a `real_demand_proportions.json` file conforming to this contract.

## Purpose
The simulation generates stochastic demand for relief vehicles (ambulances, cargo trucks, first responders) based on the aggregate output of the NMF topic modeling. 

## Expected Schema

The simulation expects a JSON file at `sumo_simulation/demand/real_demand_proportions.json` with the following structure:

```json
{
    "_meta": {
        "method": "PATH_3_DOCUMENT_WEIGHTED",
        "source": "alignment_results.json confusion matrix",
        "total_documents": 10910,
        "actionable_documents": 4478,
        "non_actionable_documents": 6432
    },
    "dispatch_proportions": {
        "ambulance": 0.6436,
        "cargo_truck": 0.1679,
        "first_responder": 0.1885
    },
    "raw_document_counts": {
        "ambulance": 2882,
        "cargo_truck": 752,
        "first_responder": 844
    }
}
```

### Key Requirements
- `dispatch_proportions`: Must contain key-value pairs where the key is one of `ambulance`, `cargo_truck`, or `first_responder`. The values must sum to 1.0 (or very close, accounting for floating point rounding).
- **No other categories** are currently supported by the SUMO vehicle mappings. Non-actionable noise is discarded before this schema is generated.

## Validation
Use `validate_lda_output.py` to ensure the NLP pipeline's output conforms to this schema before running the SUMO simulation.
