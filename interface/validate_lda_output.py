"""
validate_lda_output.py -- Schema gate for the NLP -> SUMO interface.

Validates that a demand-proportions JSON file conforms to the contract in
`interface/demand_schema.md` before it is consumed by the SUMO pipeline.

Exit codes:
    0 -- file conforms to the schema
    1 -- file is missing, unreadable, or violates the schema

Usage:
    python validate_lda_output.py <path_to_proportions_json>
"""

import json
import numbers
import sys

# The only dispatch categories the SUMO vehicle mappings support.
# Kept in sync with sumo_simulation/vehicles/vtypes.add.xml and
# interface/dispatch_category_mapping.json.
VALID_CATEGORIES = ("ambulance", "cargo_truck", "first_responder")

# Tolerance on the proportion sum, to absorb the 4-decimal rounding applied by
# compute_demand_proportions.py.
SUM_TOLERANCE = 0.01


def validate_proportions(file_path, require_all_categories=True):
    """
    Return True if `file_path` conforms to demand_schema.md, else False.

    Every rejection is reported as a single 'FAILED: ...' line. Malformed input
    must never raise -- a crash here would look like a broken validator rather
    than a rejected file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAILED: Could not read {file_path}. Error: {e}")
        return False

    if not isinstance(data, dict):
        print(f"FAILED: Top level of {file_path} must be a JSON object, "
              f"got {type(data).__name__}.")
        return False

    if "dispatch_proportions" not in data:
        print("FAILED: Missing 'dispatch_proportions' key.")
        return False

    props = data["dispatch_proportions"]

    if not isinstance(props, dict):
        print(f"FAILED: 'dispatch_proportions' must be a JSON object mapping "
              f"category -> proportion, got {type(props).__name__}.")
        return False

    if not props:
        print("FAILED: 'dispatch_proportions' is empty.")
        return False

    for k in props:
        if k not in VALID_CATEGORIES:
            print(f"FAILED: Invalid dispatch category '{k}'. "
                  f"Allowed: {set(VALID_CATEGORIES)}")
            return False

    # Reject non-numeric values before any arithmetic, so a string- or
    # null-valued file is reported rather than raising a TypeError.
    for k, v in props.items():
        if isinstance(v, bool) or not isinstance(v, numbers.Real):
            print(f"FAILED: Proportion for '{k}' must be a number, "
                  f"got {type(v).__name__} ({v!r}).")
            return False
        if v < 0.0 or v > 1.0:
            print(f"FAILED: Proportion for '{k}' must lie in [0.0, 1.0], "
                  f"got {v}.")
            return False

    if require_all_categories:
        missing = [c for c in VALID_CATEGORIES if c not in props]
        if missing:
            print(f"FAILED: Missing required dispatch categories: {missing}. "
                  f"A partial distribution would silently reallocate the whole "
                  f"fleet to the categories that are present.")
            return False

    total = sum(props.values())
    if abs(total - 1.0) > SUM_TOLERANCE:
        print(f"FAILED: Proportions do not sum to 1.0 (Sum = {total})")
        return False

    print(f"SUCCESS: {file_path} conforms to demand_schema.md.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_lda_output.py <path_to_proportions_json>")
        sys.exit(1)

    success = validate_proportions(sys.argv[1])
    sys.exit(0 if success else 1)
