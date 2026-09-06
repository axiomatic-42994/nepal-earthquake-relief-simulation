import os
import xml.etree.ElementTree as ET
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import json
import numpy as np

# Set standard styles for publication/report quality
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_context("paper", font_scale=1.5)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_dir = os.path.join(base_dir, 'output', 'visualizations')
os.makedirs(out_dir, exist_ok=True)

def plot_delivery_time_distribution():
    print("Generating Delivery-Time Distribution (Box Plot)...")
    
    dyn_xml = os.path.join(base_dir, 'output', 'tripinfo_dynamic.xml')
    sta_xml = os.path.join(base_dir, 'output', 'tripinfo_static.xml')
    
    data = []
    
    for mode, xml_file in [('Dynamic (TraCI)', dyn_xml), ('Static (Baseline)', sta_xml)]:
        if not os.path.exists(xml_file):
            print(f"Warning: {xml_file} not found, skipping.")
            continue
            
        tree = ET.parse(xml_file)
        for trip in tree.getroot().findall('tripinfo'):
            vtype = trip.attrib.get('vType', '').split('@')[0]
            if vtype in ['ambulance', 'first_responder', 'cargo_truck']:
                data.append({
                    'Mode': mode,
                    'Delivery Time (s)': float(trip.attrib['duration']),
                    'Vehicle Type': vtype.replace('_', ' ').title()
                })
                
    df = pd.DataFrame(data)
    if df.empty:
        return
        
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=df, x='Vehicle Type', y='Delivery Time (s)', hue='Mode', palette=['#2ecc71', '#e74c3c'])
    plt.title('Relief Vehicle Delivery Time Distribution\n(Real NMF Demand Proportions)')
    plt.axhline(y=300, color='r', linestyle='--', alpha=0.7, label='300s SLA Target')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'delivery_time_dist.png'), dpi=300)
    plt.close()


def plot_statistical_replication():
    print("Generating Statistical Replication Charts (N=5)...")
    seeds = [42, 101, 202, 303, 404]
    
    data = []
    
    # We parse the tripinfo files for each seed to recreate the stats
    from evaluate_results import parse_tripinfo, get_total_expected
    
    for seed in seeds:
        bg_route = os.path.join(base_dir, 'demand', f'bg_routes_{seed}.rou.xml')
        relief_route = os.path.join(base_dir, 'demand', 'relief_vehicles.rou.xml')
        
        dyn_out = os.path.join(base_dir, 'output', f'tripinfo_dynamic_{seed}.xml')
        sta_out = os.path.join(base_dir, 'output', f'tripinfo_static_{seed}.xml')
        
        total_expected = get_total_expected(relief_route)
        
        if os.path.exists(dyn_out) and os.path.exists(sta_out):
            dyn_res = parse_tripinfo(dyn_out, total_expected)
            sta_res = parse_tripinfo(sta_out, total_expected)
            
            data.append({
                'Seed': str(seed),
                'Mode': 'Dynamic (TraCI)',
                'Fulfillment (%)': dyn_res['fulfillment_rate_pct'],
                'Avg Duration (s)': dyn_res['avg_duration_sec']
            })
            
            data.append({
                'Seed': str(seed),
                'Mode': 'Static (Baseline)',
                'Fulfillment (%)': sta_res['fulfillment_rate_pct'],
                'Avg Duration (s)': sta_res['avg_duration_sec']
            })
            
    df = pd.DataFrame(data)
    if df.empty:
        print("Warning: No replication data found, skipping replication plots.")
        return
        
    # Plot 1: Fulfillment Rate across seeds
    plt.figure(figsize=(10, 5))
    sns.barplot(data=df, x='Seed', y='Fulfillment (%)', hue='Mode', palette=['#2ecc71', '#e74c3c'])
    plt.title('Mission Fulfillment Rate by Random Seed')
    plt.ylim(0, 100)
    plt.legend(loc='lower right')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'replication_fulfillment.png'), dpi=300)
    plt.close()
    
    # Plot 2: Average Duration across seeds
    plt.figure(figsize=(10, 5))
    sns.barplot(data=df, x='Seed', y='Avg Duration (s)', hue='Mode', palette=['#2ecc71', '#e74c3c'])
    plt.title('Average Delivery Duration by Random Seed')
    plt.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'replication_duration.png'), dpi=300)
    plt.close()


def plot_network_map():
    print("Generating Network Map with Damage Overlay...")
    try:
        import sumolib
    except ImportError:
        print("sumolib not found, skipping network map.")
        return
        
    net_path = os.path.join(base_dir, 'network', 'kathmandu.net.xml')
    damage_path = os.path.join(base_dir, 'damage', 'road_damage_events.json')
    
    if not os.path.exists(net_path) or not os.path.exists(damage_path):
        return
        
    net = sumolib.net.readNet(net_path)
    
    with open(damage_path, 'r') as f:
        events = json.load(f).get('blockage_events', [])
        
    fully_blocked = set()
    for e in events:
        for edge in e.get('fully_blocked_edges', []):
            fully_blocked.add(edge)
            
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # Plot all edges
    for edge in net.getEdges():
        shape = edge.getShape()
        xs = [pt[0] for pt in shape]
        ys = [pt[1] for pt in shape]
        
        # Color red and thick if blocked, otherwise thin grey
        if edge.getID() in fully_blocked:
            ax.plot(xs, ys, color='#e74c3c', linewidth=4, zorder=5)
        else:
            ax.plot(xs, ys, color='#bdc3c7', linewidth=0.5, alpha=0.6, zorder=1)
            
    # Add dummy lines for legend
    ax.plot([], [], color='#bdc3c7', label='Passable Road')
    ax.plot([], [], color='#e74c3c', linewidth=4, label='Structural Collapse (Blocked)')
    
    plt.title('Kathmandu Road Network: Earthquake Damage Zones')
    plt.axis('off')
    plt.legend(loc='lower right')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'network_damage_map.png'), dpi=300, bbox_inches='tight')
    plt.close()

if __name__ == '__main__':
    plot_delivery_time_distribution()
    plot_statistical_replication()
    plot_network_map()
    print(f"All visualizations exported to: {out_dir}")
