"""
compute_demand_proportions.py — Computes dispatch-category proportions from real NMF output.

PATH 3 (Document-Weighted Approximation): Uses the confusion matrix from alignment_results.json 
to get the exact number of documents predicted for each class, providing a document-weighted 
demand distribution without needing the raw corpus or model.pkl.
"""
import json
import os

def compute_document_proportions(alignment_path, mapping):
    with open(alignment_path) as f:
        data = json.load(f)
    
    cm = data['confusion_matrix']
    
    predicted_counts = {}
    for gt_class, predictions in cm.items():
        for pred_class, count in predictions.items():
            predicted_counts[pred_class] = predicted_counts.get(pred_class, 0) + count

    category_counts = {}
    no_dispatch_count = 0

    for pred_class, count in predicted_counts.items():
        dispatch_cat = mapping.get(pred_class, 'no_dispatch')
        if dispatch_cat == 'no_dispatch':
            no_dispatch_count += count
        else:
            category_counts[dispatch_cat] = category_counts.get(dispatch_cat, 0) + count
            
    total_actionable = sum(category_counts.values())
    
    proportions = {}
    if total_actionable > 0:
        for cat, count in sorted(category_counts.items()):
            proportions[cat] = round(count / total_actionable, 4)
            
    total_documents = total_actionable + no_dispatch_count
    return proportions, category_counts, no_dispatch_count, total_documents, predicted_counts

CLASS_TO_DISPATCH = {
    'injured_or_dead_people':           'ambulance',
    'missing_and_found_people':         'first_responder',
    'displaced_and_evacuations':        'cargo_truck',
    'requests_or_needs':                'cargo_truck',
    'infrastructure_and_utilities_damage': 'road_damage_signal',
    'donation_and_volunteering':        'no_dispatch',
    'caution_and_advice':               'no_dispatch',
    'sympathy_and_support':             'no_dispatch',
    'not_humanitarian':                 'no_dispatch',
    'other_relevant_information':       'no_dispatch',
    'personal_update':                  'no_dispatch',
    'response_efforts':                 'no_dispatch'
}

if __name__ == '__main__':
    alignment_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'lda_pipeline', 'models', 'selected', 'alignment_results.json'
    )
    alignment_path = os.path.normpath(alignment_path)
    
    proportions, counts, no_dispatch, total, pred_counts = compute_document_proportions(alignment_path, CLASS_TO_DISPATCH)
    
    print("="*60)
    print(" DEMAND PROPORTIONS — PATH 3 (Document-Weighted)")
    print(" Source: alignment_results.json confusion matrix")
    print("="*60)
    print()
    print(f"Total NMF documents:     {total}")
    print(f"Non-actionable docs:     {no_dispatch} ({no_dispatch/total*100:.1f}%)")
    print(f"Actionable docs:         {sum(counts.values())} ({sum(counts.values())/total*100:.1f}%)")
    print()
    print("--- Raw Document Counts (before renormalization) ---")
    for cat, count in sorted(counts.items()):
        print(f"  {cat:<20}: {count} documents")
    print()
    print("--- Renormalized Dispatch Proportions (sum = 1.0) ---")
    for cat, prop in proportions.items():
        print(f"  {cat:<20}: {prop:.4f}  ({prop*100:.2f}%)")
    print(f"  {'TOTAL':<20}: {sum(proportions.values()):.4f}")
    
    output = {
        '_meta': {
            'method': 'PATH_3_DOCUMENT_WEIGHTED',
            'source': 'alignment_results.json confusion matrix',
            'total_documents': total,
            'actionable_documents': sum(counts.values()),
            'non_actionable_documents': no_dispatch
        },
        'dispatch_proportions': proportions,
        'raw_document_counts': counts
    }
    
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'demand', 'real_demand_proportions.json'
    )
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=4)
        
    print(f"\nSaved to: {out_path}")
