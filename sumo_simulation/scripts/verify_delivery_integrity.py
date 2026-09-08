"""
verify_delivery_integrity.py — Cross-references tripinfo arrivalLane against
each vehicle's assigned route last edge to detect false deliveries caused by
traci.vehicle.remove() writing tripinfo records for abandoned vehicles.
"""
import os
import sys
import xml.etree.ElementTree as ET
import numpy as np

def get_route_destinations(route_file):
    """Extract the final edge for each dispatch vehicle from the routed file."""
    tree = ET.parse(route_file)
    root = tree.getroot()
    dispatch_types = ['ambulance', 'first_responder', 'cargo_truck']
    destinations = {}
    for veh in root.findall('vehicle'):
        vtype = veh.attrib.get('type', '').split('@')[0]
        if vtype in dispatch_types:
            route_node = veh.find('route')
            if route_node is not None:
                edges = route_node.attrib['edges'].split()
                if edges:
                    destinations[veh.attrib['id']] = edges[-1]
    return destinations

def verify_tripinfo(tripinfo_file, route_file, label=""):
    """Check each tripinfo record against its expected destination edge."""
    destinations = get_route_destinations(route_file)
    total_expected = len(destinations)
    
    tree = ET.parse(tripinfo_file)
    root = tree.getroot()
    dispatch_types = ['ambulance', 'first_responder', 'cargo_truck']
    trips = [t for t in root.findall('tripinfo') 
             if t.attrib.get('vType', '').split('@')[0] in dispatch_types]
    
    genuine_deliveries = []
    false_deliveries = []
    
    for t in trips:
        vid = t.attrib['id']
        arrival_lane = t.attrib.get('arrivalLane', '')
        # arrivalLane is like "edgeid_0", extract edge
        arrival_edge = '_'.join(arrival_lane.rsplit('_', 1)[:-1]) if '_' in arrival_lane else arrival_lane
        
        expected_edge = destinations.get(vid, None)
        duration = float(t.attrib['duration'])
        
        if expected_edge and arrival_edge == expected_edge:
            genuine_deliveries.append({
                'id': vid,
                'duration': duration,
                'waiting': float(t.attrib['waitingTime']),
                'arrival_edge': arrival_edge,
                'expected_edge': expected_edge
            })
        else:
            false_deliveries.append({
                'id': vid,
                'duration': duration,
                'waiting': float(t.attrib['waitingTime']),
                'arrival_edge': arrival_edge,
                'arrival_lane': arrival_lane,
                'expected_edge': expected_edge
            })
    
    # Original (buggy) metrics
    all_durations = [float(t.attrib['duration']) for t in trips]
    original_completed = len(trips)
    original_fulfilled = sum(1 for d in all_durations if d <= 300.0)
    original_fulfillment = (original_fulfilled / total_expected) * 100.0
    original_avg_dur = np.mean(all_durations) if all_durations else 0.0
    original_avg_wait = np.mean([float(t.attrib['waitingTime']) for t in trips]) if trips else 0.0
    
    # Corrected metrics (genuine deliveries only)
    corrected_completed = len(genuine_deliveries)
    genuine_durations = [d['duration'] for d in genuine_deliveries]
    genuine_waiting = [d['waiting'] for d in genuine_deliveries]
    corrected_fulfilled = sum(1 for d in genuine_durations if d <= 300.0)
    corrected_fulfillment = (corrected_fulfilled / total_expected) * 100.0
    corrected_avg_dur = np.mean(genuine_durations) if genuine_durations else 0.0
    corrected_avg_wait = np.mean(genuine_waiting) if genuine_waiting else 0.0
    corrected_stranded = total_expected - corrected_completed
    
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Total expected:       {total_expected}")
    print(f"  Tripinfo records:     {original_completed}")
    print(f"  Genuine deliveries:   {corrected_completed}")
    print(f"  False deliveries:     {len(false_deliveries)}")
    print(f"  Stranded (corrected): {corrected_stranded}")
    print(f"")
    print(f"  --- ORIGINAL (buggy) ---")
    print(f"  Fulfillment rate:     {original_fulfillment:.2f}%")
    print(f"  Avg duration:         {original_avg_dur:.2f}s")
    print(f"  Avg waiting:          {original_avg_wait:.2f}s")
    print(f"")
    print(f"  --- CORRECTED ---")
    print(f"  Fulfillment rate:     {corrected_fulfillment:.2f}%")
    print(f"  Avg duration:         {corrected_avg_dur:.2f}s")
    print(f"  Avg waiting:          {corrected_avg_wait:.2f}s")
    
    if false_deliveries:
        print(f"\n  False delivery details:")
        for fd in false_deliveries:
            print(f"    {fd['id']}: duration={fd['duration']:.1f}s, "
                  f"arrived={fd['arrival_edge']}, expected={fd['expected_edge']}, "
                  f"arrivalLane={fd['arrival_lane']}")
    
    return {
        'total_expected': total_expected,
        'original_completed': original_completed,
        'genuine_completed': corrected_completed,
        'false_deliveries': len(false_deliveries),
        'stranded': corrected_stranded,
        'original_fulfillment': original_fulfillment,
        'corrected_fulfillment': corrected_fulfillment,
        'corrected_avg_duration': corrected_avg_dur,
        'corrected_avg_waiting': corrected_avg_wait,
        'false_delivery_list': false_deliveries
    }


if __name__ == '__main__':
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    route_file = os.path.join(base, 'demand', 'relief_vehicles_routed.rou.xml')
    
    seeds = [42, 101, 202, 303, 404]
    
    # Verify dynamic mode across all seeds
    dyn_results = []
    sta_results = []
    
    for seed in seeds:
        dyn_file = os.path.join(base, 'output', f'tripinfo_dynamic_{seed}.xml')
        sta_file = os.path.join(base, 'output', f'tripinfo_static_{seed}.xml')
        
        if os.path.exists(dyn_file):
            r = verify_tripinfo(dyn_file, route_file, f"Dynamic seed={seed}")
            dyn_results.append(r)
        else:
            print(f"WARNING: {dyn_file} not found")
            
        if os.path.exists(sta_file):
            r = verify_tripinfo(sta_file, route_file, f"Static seed={seed}")
            sta_results.append(r)
        else:
            print(f"WARNING: {sta_file} not found")
    
    # Also check the unseeded files
    for mode in ['dynamic', 'static']:
        f = os.path.join(base, 'output', f'tripinfo_{mode}.xml')
        if os.path.exists(f):
            verify_tripinfo(f, route_file, f"{mode.title()} (unseeded)")
    
    # Summary across 5 seeds
    if dyn_results:
        print(f"\n{'='*60}")
        print(f"  AGGREGATE (5-seed mean ± std)")
        print(f"{'='*60}")
        
        dyn_fulfill = [r['corrected_fulfillment'] for r in dyn_results]
        dyn_dur = [r['corrected_avg_duration'] for r in dyn_results]
        dyn_wait = [r['corrected_avg_waiting'] for r in dyn_results]
        dyn_strand = [r['stranded'] for r in dyn_results]
        dyn_false = [r['false_deliveries'] for r in dyn_results]
        
        print(f"  Dynamic (corrected):")
        print(f"    Fulfillment:  {np.mean(dyn_fulfill):.2f}% (± {np.std(dyn_fulfill):.2f}%)")
        print(f"    Avg duration: {np.mean(dyn_dur):.2f}s (± {np.std(dyn_dur):.2f}s)")
        print(f"    Avg waiting:  {np.mean(dyn_wait):.2f}s (± {np.std(dyn_wait):.2f}s)")
        print(f"    Stranded:     {np.mean(dyn_strand):.2f} (± {np.std(dyn_strand):.2f})")
        print(f"    False deliv:  {np.mean(dyn_false):.2f} (± {np.std(dyn_false):.2f})")
        
    if sta_results:
        sta_fulfill = [r['corrected_fulfillment'] for r in sta_results]
        sta_dur = [r['corrected_avg_duration'] for r in sta_results]
        sta_wait = [r['corrected_avg_waiting'] for r in sta_results]
        sta_strand = [r['stranded'] for r in sta_results]
        sta_false = [r['false_deliveries'] for r in sta_results]
        
        print(f"\n  Static (control — should have 0 false deliveries):")
        print(f"    Fulfillment:  {np.mean(sta_fulfill):.2f}% (± {np.std(sta_fulfill):.2f}%)")
        print(f"    Avg duration: {np.mean(sta_dur):.2f}s (± {np.std(sta_dur):.2f}s)")
        print(f"    Avg waiting:  {np.mean(sta_wait):.2f}s (± {np.std(sta_wait):.2f}s)")
        print(f"    Stranded:     {np.mean(sta_strand):.2f} (± {np.std(sta_strand):.2f})")
        print(f"    False deliv:  {np.mean(sta_false):.2f} (± {np.std(sta_false):.2f})")
    
    if dyn_results and sta_results:
        gain = np.mean(dyn_fulfill) - np.mean(sta_fulfill)
        print(f"\n  Fulfillment gain (corrected): +{gain:.2f}pp")
