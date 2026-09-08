"""
run_all_windows.py — Orchestrates multi-window simulation across the disaster period.

NOTE — SCOPE DECISION (Part E, Option 1):
    This script is NOT exercised for the final reported results. The underlying
    NLP dataset (CrisisNLP 2015 Nepal Earthquake) has no real per-day or per-window
    tweet timestamp breakdown — the teammate's NMF pipeline produces a single
    aggregate topic distribution across the entire corpus. Therefore, the final
    simulation uses one static aggregate demand scenario, not a 25-day loop.

    This code is retained as an available capability: if real temporal data were
    available in the future, it could drive a multi-window simulation. It should
    not be cited as producing any of the results in the paper.

!! DOES NOT CURRENTLY RUN — see BROKEN_PRECONDITIONS below. !!
    An audit pass found this script drifted out of sync with the modules it
    calls. It is left in place as a design sketch (the scope decision above is
    the reason it was never finished), but `--run` now aborts with a checklist
    instead of failing halfway through. The most important reason for the abort:
    step 4 below COPIES OVER demand/relief_vehicles_routed.rou.xml, the exact
    file that reproduces every published result. Running this script as written
    would destroy the reproducibility of the reported numbers.

For a specified list of time windows, this script:
1. Pulls that window's topic proportions from the input JSON.
2. Extracts just that window into a temporary JSON and runs generate_demand.py.
3. Computes baseline routes using duarouter.
4. Runs both dynamic and static simulation modes for the window.
5. Evaluates tripinfo and appends the metrics to a CSV table.

Usage:
    python run_all_windows.py --subset "day1,day3,day10,day17,day25"
"""

import os
import sys
import json
import subprocess
import csv
from evaluate_results import parse_tripinfo

# Every way this script is out of step with the code it drives. Each line was
# verified against the current modules during the audit pass; fix them all
# before removing the guard in main().
BROKEN_PRECONDITIONS = [
    "DESTRUCTIVE: run_window() shutil.copy()s the window's routes over "
    "demand/relief_vehicles_routed.rou.xml, the file that reproduces every "
    "published result. Give run_simulation.py a --routes flag instead.",

    "generate_demand.py no longer accepts --lda-input or --topic-map; it takes "
    "--demand-input (a real_demand_proportions.json) and --net.",

    "parse_tripinfo() now requires a second argument, total_expected. "
    "run_window() still calls parse_tripinfo(path) with one argument.",

    "demand/mock_lda_input.json does not exist in the repository; there is no "
    "per-window input file to read, and none can be built honestly because the "
    "CrisisNLP corpus carries no usable tweet timestamps.",

    "duarouter is invoked as 'duarouter.exe', so this cannot run off Windows.",
]


def assert_runnable():
    """Refuse to start rather than fail destructively halfway through."""
    print("run_all_windows.py cannot run: it is out of sync with the current pipeline.\n")
    for i, problem in enumerate(BROKEN_PRECONDITIONS, 1):
        print(f"  {i}. {problem}\n")
    print("This script produced none of the reported results (see the scope note "
          "in the module docstring).")
    raise SystemExit(2)


def run_window(window_data, base_dir, total_dispatches):
    """Executes the pipeline for a single time window."""
    window_id = window_data['window_id']
    print(f"\n--- Processing Window: {window_id} ---")
    
    # 1. Write temporary single-window JSON for generate_demand.py
    temp_lda_path = os.path.join(base_dir, 'demand', f'temp_lda_{window_id}.json')
    with open(temp_lda_path, 'w') as f:
        json.dump({'total_dispatches': total_dispatches, 'time_windows': [window_data]}, f)
        
    routes_raw = os.path.join(base_dir, 'demand', f'relief_{window_id}.rou.xml')
    routes_routed = os.path.join(base_dir, 'demand', f'relief_{window_id}_routed.rou.xml')
    
    # 2. Regenerate demand
    print("  -> Generating demand...")
    subprocess.run([
        'python', os.path.join(base_dir, 'scripts', 'generate_demand.py'),
        '--lda-input', temp_lda_path,
        '--net', os.path.join(base_dir, 'network', 'kathmandu.net.xml'),
        '--topic-map', os.path.join(base_dir, 'vehicles', 'topic_vehicle_map.json'),
        '--output', routes_raw,
        '--seed', '42'
    ], check=True)
    
    # 3. Route demand
    print("  -> Precomputing baseline routes...")
    sumo_home = os.environ.get('SUMO_HOME', '')
    subprocess.run([
        os.path.join(sumo_home, 'bin', 'duarouter.exe'),
        '-n', os.path.join(base_dir, 'network', 'kathmandu.net.xml'),
        '-r', routes_raw,
        '-o', routes_routed,
        '--ignore-errors', 'true', '--no-warnings', 'true'
    ], check=True)
    
    # 4. Run simulations
    results = {}
    for mode in ['dynamic', 'static']:
        print(f"  -> Running {mode} mode...")
        tripinfo_out = os.path.join(base_dir, 'output', f'tripinfo_{window_id}_{mode}.xml')
        
        # Modify run_simulation args to pass the correct routes
        # Note: run_simulation.py currently hardcodes routes_path. We'll pass it via env or assume we modify run_simulation to take --routes
        cmd = [
            'python', os.path.join(base_dir, 'scripts', 'run_simulation.py'),
            '--mode', mode,
            '--output', tripinfo_out
        ]
        
        # We temporarily overwrite relief_vehicles_routed.rou.xml so run_simulation.py picks it up without modification
        import shutil
        shutil.copy(routes_routed, os.path.join(base_dir, 'demand', 'relief_vehicles_routed.rou.xml'))
        
        subprocess.run(cmd, check=True)
        
        # Parse metrics
        metrics = parse_tripinfo(tripinfo_out)
        results[mode] = metrics
        
    return results

def main():
    # Abort before touching anything. The first broken precondition is
    # destructive, so this guard runs ahead of every file operation.
    assert_runnable()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mock_input = os.path.join(base_dir, 'demand', 'mock_lda_input.json')

    with open(mock_input, 'r') as f:
        data = json.load(f)
        
    windows = data.get('time_windows', [])
    csv_out = os.path.join(base_dir, 'output', 'multi_window_results.csv')
    
    # Define CSV structure
    headers = [
        "Window_ID", "Mode", "Dispatched", "Completed", "Stranded", 
        "Fulfillment_Pct", "Avg_Duration_s", "Avg_Waiting_s"
    ]
    
    print(f"Discovered {len(windows)} windows in mock data.")
    print(f"Results will be appended to: {csv_out}")
    print("CSV Structure:")
    print(" | ".join(headers))
    
    print("\n[STARTING BATCH RUN]")
    
    with open(csv_out, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(headers)
        
        for i, window in enumerate(windows):
            if '--run' not in sys.argv:
                print(f"Would process window: {window['window_id']} (Pass --run to execute)")
                continue
                
            print(f"\n=========================================")
            print(f" Orchestrating Window {i+1}/{len(windows)}")
            print(f"=========================================")
            
            try:
                results = run_window(window, base_dir, data.get('total_dispatches', 151))
                
                # Write results to CSV for both modes
                for mode in ['dynamic', 'static']:
                    metrics = results[mode]
                    row = [
                        window['window_id'],
                        mode,
                        metrics['total_expected'],
                        metrics['completed'],
                        metrics['uncompleted_or_stranded'],
                        f"{metrics['fulfillment_rate_pct']:.1f}",
                        f"{metrics['avg_duration_sec']:.1f}",
                        f"{metrics['avg_waiting_time_sec']:.1f}"
                    ]
                    writer.writerow(row)
                    
            except Exception as e:
                # A bare 'print and carry on' here would emit a CSV that looks
                # complete while silently missing windows. Record the failure in
                # the CSV itself and re-raise so a batch failure cannot be
                # mistaken for a batch success.
                print(f"ERROR processing window {window['window_id']}: "
                      f"{type(e).__name__}: {e}", file=sys.stderr)
                writer.writerow([window['window_id'], 'FAILED',
                                 '', '', '', '', '', f"{type(e).__name__}: {e}"])
                raise

    if '--run' in sys.argv:
        print(f"\n[BATCH RUN COMPLETE] Results saved to {csv_out}")

if __name__ == '__main__':
    main()
