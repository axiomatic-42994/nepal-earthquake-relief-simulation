"""
compute_demand_proportions.py — Computes dispatch-category proportions from real NMF output.

PATH 3 (Document-Weighted Approximation): Uses the confusion matrix from alignment_results.json
to get the exact number of documents predicted for each class, providing a document-weighted
demand distribution without needing the raw corpus or model.pkl.

The emitted JSON conforms to the contract in interface/demand_schema.md and must pass
interface/validate_lda_output.py.
"""
import json
import os
import sys

# Canonical mapping from NMF ground-truth class -> dispatch category.
# Kept in sync with interface/dispatch_category_mapping.json and
# sumo_simulation/vehicles/topic_vehicle_map.json.
CLASS_TO_DISPATCH = {
    'injured_or_dead_people':              'ambulance',
    'missing_and_found_people':            'first_responder',
    'displaced_and_evacuations':           'cargo_truck',
    'requests_or_needs':                   'cargo_truck',
    'infrastructure_and_utilities_damage': 'road_damage_signal',
    'donation_and_volunteering':           'no_dispatch',
    'caution_and_advice':                  'no_dispatch',
    'sympathy_and_support':                'no_dispatch',
    'not_humanitarian':                    'no_dispatch',
    'other_relevant_information':          'no_dispatch',
    'personal_update':                     'no_dispatch',
    'response_efforts':                    'no_dispatch'
}

# Categories backed by an actual SUMO vehicle type, and therefore the only ones
# allowed to appear in dispatch_proportions.
DISPATCHABLE_CATEGORIES = ('ambulance', 'cargo_truck', 'first_responder')

# road_damage_signal is a declared-but-descoped integration path: the
# infrastructure_and_utilities_damage class has zero topics assigned by the NMF
# model, so it carries no real data. It is counted into its own bucket rather
# than folded into the dispatch proportions — emitting it there would produce a
# category the SUMO vehicle mappings cannot honour, and would fail schema
# validation downstream.
DESCOPED_CATEGORIES = ('road_damage_signal',)


def compute_document_proportions(alignment_path, mapping):
    """
    Aggregate the alignment confusion matrix into dispatch-category document counts.

    Returns (proportions, category_counts, no_dispatch_count, total_documents,
             predicted_counts, descoped_counts).
    """
    try:
        with open(alignment_path, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            "Alignment results not found at:\n  {}\n"
            "This file is produced by the NMF pipeline in lda_pipeline/. Run that "
            "pipeline first, or check that the lda_pipeline submodule is actually "
            "checked out (see the repository README).".format(alignment_path)
        ) from None

    if 'confusion_matrix' not in data:
        raise KeyError(
            "'confusion_matrix' key missing from {}. Top-level keys present: {}"
            .format(alignment_path, sorted(data))
        )

    cm = data['confusion_matrix']

    predicted_counts = {}
    for gt_class, predictions in cm.items():
        for pred_class, count in predictions.items():
            predicted_counts[pred_class] = predicted_counts.get(pred_class, 0) + count

    # Previously an unmapped class silently fell through to 'no_dispatch', which
    # would quietly shrink the actionable pool. Fail loudly instead.
    unknown = sorted(set(predicted_counts) - set(mapping))
    if unknown:
        raise KeyError(
            "Confusion matrix contains predicted classes with no dispatch mapping: {}. "
            "Add them to CLASS_TO_DISPATCH (and to "
            "interface/dispatch_category_mapping.json) before rerunning.".format(unknown)
        )

    category_counts = {}
    descoped_counts = {}
    no_dispatch_count = 0

    for pred_class, count in predicted_counts.items():
        dispatch_cat = mapping[pred_class]
        if dispatch_cat == 'no_dispatch':
            no_dispatch_count += count
        elif dispatch_cat in DESCOPED_CATEGORIES:
            descoped_counts[dispatch_cat] = descoped_counts.get(dispatch_cat, 0) + count
        elif dispatch_cat in DISPATCHABLE_CATEGORIES:
            category_counts[dispatch_cat] = category_counts.get(dispatch_cat, 0) + count
        else:
            raise ValueError(
                "Class '{}' maps to '{}', which is neither a dispatchable SUMO "
                "category {} nor an explicitly descoped one {}."
                .format(pred_class, dispatch_cat,
                        DISPATCHABLE_CATEGORIES, DESCOPED_CATEGORIES)
            )

    total_actionable = sum(category_counts.values())

    proportions = {}
    if total_actionable > 0:
        for cat, count in sorted(category_counts.items()):
            proportions[cat] = round(count / total_actionable, 4)

    total_documents = total_actionable + no_dispatch_count + sum(descoped_counts.values())
    return (proportions, category_counts, no_dispatch_count, total_documents,
            predicted_counts, descoped_counts)


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alignment_path = os.path.normpath(os.path.join(
        base_dir, '..', 'lda_pipeline', 'models', 'selected', 'alignment_results.json'
    ))

    (proportions, counts, no_dispatch, total,
     pred_counts, descoped) = compute_document_proportions(alignment_path,
                                                           CLASS_TO_DISPATCH)

    print("=" * 60)
    print(" DEMAND PROPORTIONS — PATH 3 (Document-Weighted)")
    print(" Source: alignment_results.json confusion matrix")
    print("=" * 60)
    print()
    print(f"Total NMF documents:     {total}")
    print(f"Non-actionable docs:     {no_dispatch} ({no_dispatch/total*100:.1f}%)")
    print(f"Actionable docs:         {sum(counts.values())} ({sum(counts.values())/total*100:.1f}%)")

    descoped_total = sum(descoped.values())
    if descoped_total:
        print()
        print(f"WARNING: {descoped_total} document(s) mapped to descoped categories {dict(descoped)}.")
        print("         These are EXCLUDED from dispatch_proportions because no SUMO")
        print("         vehicle type implements them. The infrastructure-damage ->")
        print("         road-closure integration was descoped as not viable; read the")
        print("         project reports before acting on this number.")
    else:
        print("Descoped-category docs:  0 (road_damage_signal path carries no data, as expected)")
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

    out_path = os.path.join(base_dir, 'demand', 'real_demand_proportions.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4)

    print(f"\nSaved to: {out_path}")


if __name__ == '__main__':
    try:
        main()
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
