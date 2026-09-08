"""
Model selection module: picks the winning topic model based on the empirical leaderboard,
serializes selected artifacts to models/selected/, and generates a selection memo with topic interpretations.
"""
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from gensim.corpora import Dictionary, MmCorpus
from gensim.models import LdaModel

from ..utils.io import load_config, load_json, save_json, ensure_dir, load_pickle, get_logger
from ..utils.viz import plot_confusion_matrix

logger = get_logger("models.select")


def select_and_package_winning_model(
    config: Optional[Dict[str, Any]] = None,
    leaderboard_csv_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Select the top-ranked model from the leaderboard, export its artifacts to models/selected/,
    and write a detailed selection memo.
    """
    if config is None:
        config = load_config()

    paths_cfg = config.get("paths", {})
    if leaderboard_csv_path is None:
        leaderboard_csv_path = paths_cfg.get("leaderboard_file", "reports/model_leaderboard.csv")

    lb_path = Path(leaderboard_csv_path)
    if not lb_path.exists():
        raise FileNotFoundError(f"Leaderboard CSV not found at: {lb_path}")

    leaderboard_df = pd.read_csv(lb_path)
    winner_row = leaderboard_df.iloc[0]
    winner_cp_name = winner_row["checkpoint_name"]
    model_type = winner_row["model_type"]
    winner_k = int(winner_row["k"])

    logger.info(f"🏆 Winning Model Selected: '{winner_cp_name}' (Rank 1, Composite Score: {winner_row['composite_score']:.4f})")

    checkpoints_dir = Path(paths_cfg.get("checkpoints_dir", "models/checkpoints"))
    winner_src_dir = checkpoints_dir / winner_cp_name
    selected_dir = Path(paths_cfg.get("selected_model_dir", "models/selected"))
    ensure_dir(selected_dir)

    # Copy checkpoint files into selected directory
    for item in winner_src_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, selected_dir / item.name)

    # Load alignment results
    alignment_data = load_json(winner_src_dir / "alignment_results.json")
    metadata = load_json(winner_src_dir / "metadata.json")

    # Load preprocessed dataset to extract representative tweets per topic
    processed_df_file = paths_cfg.get("processed_tokens_file", "data/processed/nepal_eq_processed.parquet")
    dict_file = paths_cfg.get("dictionary_file", "data/processed/dictionary.gensim")
    bow_file = paths_cfg.get("corpus_bow_file", "data/processed/corpus_bow.mm")

    try:
        df_processed = pd.read_parquet(processed_df_file)
    except Exception:
        df_processed = pd.read_csv(Path(processed_df_file).with_suffix(".csv"))

    dictionary = Dictionary.load(dict_file)
    corpus_bow = list(MmCorpus(bow_file))

    # Generate topic interpretation summary
    topic_top_words = metadata["topic_top_words"]
    topic_mapping = alignment_data["topic_to_label_mapping"]
    topic_sim_scores = alignment_data["topic_similarity_scores"]

    # Extract top representative tweets for each topic
    topic_interpretations = []
    
    # Calculate topic probabilities for all docs
    if "gensim" in model_type:
        model_obj = LdaModel.load(str(selected_dir / "model.gensim"))
        doc_topic_probs = [dict(model_obj.get_document_topics(doc, minimum_probability=0.0)) for doc in corpus_bow]
    else:
        model_obj = load_pickle(selected_dir / "model.pkl")
        from gensim.matutils import corpus2csc
        csc = corpus2csc(corpus_bow, num_terms=len(dictionary))
        doc_term = csc.T.tocsr()
        doc_topic_probs_arr = model_obj.transform(doc_term)
        doc_topic_probs = [{t_idx: prob for t_idx, prob in enumerate(row)} for row in doc_topic_probs_arr]

    for t_idx in range(winner_k):
        t_key = f"topic_{t_idx}"
        keywords = topic_top_words.get(t_key, [])
        mapped_class = topic_mapping.get(t_key, "Unknown")
        sim_score = topic_sim_scores.get(t_key, 0.0)

        # Find top 3 documents with highest probability for this topic
        top_doc_indices = sorted(
            range(len(doc_topic_probs)),
            key=lambda i: doc_topic_probs[i].get(t_idx, 0.0),
            reverse=True
        )[:3]
        
        sample_tweets = [df_processed.iloc[i]["text"] for i in top_doc_indices]

        topic_interpretations.append({
            "topic_id": t_idx,
            "topic_label": f"{mapped_class.title().replace('_', ' ')} (T{t_idx})",
            "mapped_ground_truth_class": mapped_class,
            "semantic_match_similarity": sim_score,
            "top_keywords": keywords[:10],
            "representative_tweets": sample_tweets
        })

    # Save packaged topic schema
    save_json(topic_interpretations, selected_dir / "topic_schema.json")

    # Plot confusion matrix for winning model
    if "confusion_matrix" in alignment_data:
        cm_df = pd.DataFrame(alignment_data["confusion_matrix"])
        figures_dir = paths_cfg.get("figures_dir", "reports/figures")
        plot_confusion_matrix(
            cm_df,
            output_path=f"{figures_dir}/confusion_matrix.png",
            title=f"Topic Alignment Matrix: {winner_cp_name} (K={winner_k})"
        )

    # Generate Selection Memo Markdown
    memo_lines = [
        f"# Model Selection Memo: {winner_cp_name}",
        "",
        "## 1. Executive Summary",
        f"- **Selected Candidate:** `{winner_row['model_type']}`",
        f"- **Optimal Number of Topics ($K$):** `{winner_k}`",
        f"- **Rank:** 1 / {len(leaderboard_df)} tested configurations",
        f"- **Composite Score:** `{winner_row['composite_score']:.4f}`",
        f"- **Topic Coherence ($C_v$):** `{winner_row['coherence_c_v']:.4f}`",
        f"- **Topic Coherence ($U_{{mass}}$):** `{winner_row['coherence_u_mass']:.4f}`",
        f"- **Semantic Alignment Similarity:** `{winner_row['mean_semantic_similarity']:.4f}`",
        f"- **Normalized Mutual Information (NMI):** `{winner_row['normalized_mutual_info']:.4f}`",
        f"- **Alignment Macro-F1:** `{winner_row['alignment_macro_f1']:.4f}`",
        "",
        "## 2. Empirical Rationale",
        "The winning model was chosen based on a balanced multi-criteria evaluation that jointly rewards:",
        "1. **Semantic Interpretability & Coherence ($C_v$):** Ensures discovered word clusters form cohesive human concepts.",
        "2. **Ground-Truth Alignment:** Maximizes semantic cosine similarity and mutual information against the human-annotated crisis taxonomy.",
        "3. **Topic Granularity ($K$):** Sufficiently granular to separate critical disaster dimensions (medical, rescue, shelter, casualties, donations) without over-fragmentation.",
        "",
        "## 3. Discovered Humanitarian Topics",
        "",
        "| Topic ID | Mapped Humanitarian Need | Cosine Sim | Top Keywords |",
        "|---|---|---|---|"
    ]

    for item in topic_interpretations:
        kw_str = ", ".join(item["top_keywords"][:6])
        memo_lines.append(f"| Topic {item['topic_id']} | **{item['mapped_ground_truth_class']}** | {item['semantic_match_similarity']:.3f} | `{kw_str}` |")

    memo_lines.extend([
        "",
        "## 4. Topic Details & Representative Tweets",
        ""
    ])

    for item in topic_interpretations:
        memo_lines.append(f"### Topic {item['topic_id']}: {item['mapped_ground_truth_class']}")
        memo_lines.append(f"- **Top Keywords:** {', '.join(item['top_keywords'])}")
        memo_lines.append(f"- **Semantic Match Similarity:** {item['semantic_match_similarity']:.3f}")
        memo_lines.append("- **Representative Tweets:**")
        for tweet in item["representative_tweets"]:
            clean_t = tweet.replace("\n", " ").strip()
            memo_lines.append(f"  > *\"{clean_t}\"*")
        memo_lines.append("")

    memo_content = "\n".join(memo_lines)
    memo_file = selected_dir / "selection_memo.md"
    with open(memo_file, "w", encoding="utf-8") as f:
        f.write(memo_content)
    logger.info(f"Generated model selection memo at: {memo_file}")

    return {
        "winning_checkpoint": winner_cp_name,
        "model_type": model_type,
        "k": winner_k,
        "composite_score": float(winner_row["composite_score"]),
        "selection_memo_path": str(memo_file)
    }


if __name__ == "__main__":
    select_and_package_winning_model()
