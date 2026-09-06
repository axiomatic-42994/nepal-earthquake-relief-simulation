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
                print(f"Error processing window {window['window_id']}: {e}")
                
    if '--run' in sys.argv:
        print(f"\n[BATCH RUN COMPLETE] Results saved to {csv_out}")

if __name__ == '__main__':
    main()
