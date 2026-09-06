import json
import sys

def validate_proportions(file_path):
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAILED: Could not read {file_path}. Error: {e}")
        return False
        
    if "dispatch_proportions" not in data:
        print("FAILED: Missing 'dispatch_proportions' key.")
        return False
        
    props = data["dispatch_proportions"]
    
    valid_keys = {"ambulance", "cargo_truck", "first_responder"}
    for k in props.keys():
        if k not in valid_keys:
            print(f"FAILED: Invalid dispatch category '{k}'. Allowed: {valid_keys}")
            return False
            
    total = sum(props.values())
    if abs(total - 1.0) > 0.01:
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
