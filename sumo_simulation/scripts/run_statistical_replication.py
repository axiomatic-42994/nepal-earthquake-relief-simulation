import os
import sys
import subprocess
import json
import numpy as np
from evaluate_results import parse_tripinfo, get_total_expected

def run_replications():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sumo_home = os.environ.get("SUMO_HOME")
    random_trips = os.path.join(sumo_home, "tools", "randomTrips.py")
    
    seeds = [42, 101, 202, 303, 404]
    
    results = {
        'dynamic': [],
        'static': []
    }
    
    print(f"Starting statistical replication across {len(seeds)} random seeds...")
    
    for seed in seeds:
        print(f"\n=======================================")
        print(f" REPLICATION RUN: SEED {seed}")
        print(f"=======================================")
        
        bg_route_file = os.path.join(base_dir, 'demand', f'bg_routes_{seed}.rou.xml')
        bg_trip_file = os.path.join(base_dir, 'demand', f'bg_trips_{seed}.rou.xml')
        
        # 1. Generate new background traffic for this seed
        print("Generating stochastic background traffic...")
        subprocess.run([
            "python", random_trips,
            "-n", os.path.join(base_dir, 'network', 'kathmandu.net.xml'),
            "-o", bg_trip_file,
            "-r", bg_route_file,
            "--seed", str(seed),
            "--vehicle-class", "passenger",
            "--vclass", "passenger",
            "--prefix", f"bg_{seed}_",
            "--period", "3.0"
        ], check=True)
        
        # 2. Run Dynamic Simulation
        print("\nRunning Dynamic TraCI Simulation...")
        dyn_out = os.path.join(base_dir, 'output', f'tripinfo_dynamic_{seed}.xml')
        subprocess.run([
            "python", os.path.join(base_dir, "scripts", "run_simulation.py"),
            "--mode", "dynamic",
            "--seed", str(seed),
            "--background", bg_route_file,
            "--output", dyn_out
        ], check=True)
        
        # 3. Run Static Simulation
        print("\nRunning Static Baseline Simulation...")
        sta_out = os.path.join(base_dir, 'output', f'tripinfo_static_{seed}.xml')
        subprocess.run([
            "python", os.path.join(base_dir, "scripts", "run_simulation.py"),
            "--mode", "static",
            "--seed", str(seed),
            "--background", bg_route_file,
            "--output", sta_out
        ], check=True)
        
        # 4. Evaluate and Store
        print("\nEvaluating results...")
        route_file = os.path.join(base_dir, 'demand', 'relief_vehicles.rou.xml')
        total_expected = get_total_expected(route_file)
        
        dyn_res = parse_tripinfo(dyn_out, total_expected)
        sta_res = parse_tripinfo(sta_out, total_expected)
        
        results['dynamic'].append(dyn_res)
        results['static'].append(sta_res)
        
        print(f"[Seed {seed}] Dynamic - Fulfillment: {dyn_res['fulfillment_rate_pct']:.1f}%, Avg Duration: {dyn_res['avg_duration_sec']:.1f}s")
        print(f"[Seed {seed}] Static  - Fulfillment: {sta_res['fulfillment_rate_pct']:.1f}%, Avg Duration: {sta_res['avg_duration_sec']:.1f}s")

    # Calculate statistics
    print("\n\n" + "="*50)
    print(" STATISTICAL REPLICATION SUMMARY (N=5)")
    print("="*50)
    
    metrics = ['fulfillment_rate_pct', 'avg_duration_sec', 'avg_waiting_time_sec', 'uncompleted_or_stranded']
    
    for mode in ['dynamic', 'static']:
        print(f"\n--- {mode.upper()} MODE ---")
        for metric in metrics:
            vals = [r[metric] for r in results[mode]]
            mean_val = np.mean(vals)
            std_val = np.std(vals)
            print(f" {metric:<30}: Mean = {mean_val:>8.2f}  |  StdDev = {std_val:>6.2f}")
            
    # Rerouting efficiency (Delta)
    print("\n--- COMPARATIVE EFFICIENCY (DYNAMIC VS STATIC) ---")
    fulfillment_deltas = [results['dynamic'][i]['fulfillment_rate_pct'] - results['static'][i]['fulfillment_rate_pct'] for i in range(len(seeds))]
    duration_deltas = [results['static'][i]['avg_duration_sec'] - results['dynamic'][i]['avg_duration_sec'] for i in range(len(seeds))]
    
    print(f" Fulfillment Rate Gain      : Mean = +{np.mean(fulfillment_deltas):.2f}%  |  StdDev = {np.std(fulfillment_deltas):.2f}%")
    print(f" Delivery Time Saved (sec)  : Mean = +{np.mean(duration_deltas):.2f}s  |  StdDev = {np.std(duration_deltas):.2f}s")
    
if __name__ == '__main__':
    run_replications()
