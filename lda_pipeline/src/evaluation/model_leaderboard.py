"""
Model leaderboard generator: evaluates all candidate checkpoints on topic coherence
and ground-truth alignment, ranks candidates, and exports comparative reports & plots.
"""
from pathlib import Path
from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np
from gensim.corpora import Dictionary, MmCorpus
from gensim.models import LdaModel
from scipy.sparse import csr_matrix
from gensim.matutils import corpus2csc

from .coherence import compute_topic_coherence
from .ground_truth_alignment import evaluate_ground_truth_alignment
from ..utils.io import load_config, load_json, save_json, ensure_dir, load_pickle, get_logger
from ..utils.viz import plot_coherence_curves, plot_confusion_matrix

logger = get_logger("evaluation.leaderboard")


def get_dominant_topics(
    model_type: str,
    model: Any,
    corpus_bow: List[Any],
    corpus_tfidf: List[Any],
    dictionary: Dictionary
) -> List[int]:
    """Extract dominant topic index for each document in corpus."""
    dominant_topics = []

    if "gensim" in model_type:
        for doc in corpus_bow:
            topic_probs = model.get_document_topics(doc, minimum_probability=0.0)
            if topic_probs:
                best_topic = max(topic_probs, key=lambda x: x[1])[0]
            else:
                best_topic = 0
            dominant_topics.append(int(best_topic))
    elif "sklearn_lda" in model_type:
        csc = corpus2csc(corpus_bow, num_terms=len(dictionary))
        doc_term = csc.T.tocsr()
        doc_topic_dist = model.transform(doc_term)
        dominant_topics = [int(np.argmax(dist)) for dist in doc_topic_dist]
    elif "sklearn_nmf" in model_type:
        csc = corpus2csc(corpus_tfidf, num_terms=len(dictionary))
        doc_term = csc.T.tocsr()
        doc_topic_dist = model.transform(doc_term)
        dominant_topics = [int(np.argmax(dist)) for dist in doc_topic_dist]
    else:
        # Default fallback
        dominant_topics = [0] * len(corpus_bow)

    return dominant_topics


def build_leaderboard(
    config: Optional[Dict[str, Any]] = None,
    checkpoints_dir: Optional[str] = None
) -> pd.DataFrame:
    """
    Evaluate all trained checkpoints and construct a ranked leaderboard.
    """
    if config is None:
        config = load_config()

    paths_cfg = config.get("paths", {})
    if checkpoints_dir is None:
        checkpoints_dir = paths_cfg.get("checkpoints_dir", "models/checkpoints")

    checkpoints_path = Path(checkpoints_dir)
    if not checkpoints_path.exists():
        raise FileNotFoundError(f"Checkpoints directory does not exist: {checkpoints_path}")

    # Load preprocessed resources
    processed_df_file = paths_cfg.get("processed_tokens_file", "data/processed/nepal_eq_processed.parquet")
    dict_file = paths_cfg.get("dictionary_file", "data/processed/dictionary.gensim")
    bow_file = paths_cfg.get("corpus_bow_file", "data/processed/corpus_bow.mm")
    tfidf_file = paths_cfg.get("corpus_tfidf_file", "data/processed/corpus_tfidf.mm")

    logger.info("Loading preprocessed dataset and corpus...")
    try:
        df_processed = pd.read_parquet(processed_df_file)
    except Exception:
        df_processed = pd.read_csv(Path(processed_df_file).with_suffix(".csv"))

    dictionary = Dictionary.load(dict_file)
    corpus_bow = list(MmCorpus(bow_file))
    corpus_tfidf = list(MmCorpus(tfidf_file))
    doc_tokens = df_processed["tokens"].tolist()
    ground_truth = df_processed["class_label"].tolist() if "class_label" in df_processed.columns else ["unknown"] * len(df_processed)

    checkpoint_folders = [p for p in checkpoints_path.iterdir() if p.is_dir() and (p / "metadata.json").exists()]
    logger.info(f"Found {len(checkpoint_folders)} checkpoint models to evaluate.")

    records = []

    for cp_dir in sorted(checkpoint_folders):
        meta = load_json(cp_dir / "metadata.json")
        model_type = meta["model_type"]
        k = meta["k"]
        topic_top_words = meta["topic_top_words"]
        logger.info(f"Evaluating checkpoint: {cp_dir.name} (model={model_type}, K={k})...")

        # 1. Coherence Evaluation
        topic_word_lists = [topic_top_words[f"topic_{i}"] for i in range(k)]
        coherence_scores = compute_topic_coherence(
            topic_words=topic_word_lists,
            texts=doc_tokens,
            dictionary=dictionary,
            corpus=corpus_bow,
            top_n=config.get("evaluation", {}).get("top_n_words", 10)
        )
        c_v = coherence_scores.get("c_v", np.nan)
        u_mass = coherence_scores.get("u_mass", np.nan)

        # 2. Load model object to compute dominant topics
        model_obj = None
        if "gensim" in model_type:
            model_obj = LdaModel.load(str(cp_dir / "model.gensim"))
        elif "sklearn" in model_type:
            model_obj = load_pickle(cp_dir / "model.pkl")

        doc_dominant_topics = get_dominant_topics(
            model_type=model_type,
            model=model_obj,
            corpus_bow=corpus_bow,
            corpus_tfidf=corpus_tfidf,
            dictionary=dictionary
        )

        # 3. Ground Truth Alignment
        alignment_res = evaluate_ground_truth_alignment(
            topic_top_words=topic_top_words,
            doc_dominant_topics=doc_dominant_topics,
            ground_truth_labels=ground_truth,
            embedding_model_name=config.get("evaluation", {}).get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
        )

        # Save alignment details inside checkpoint
        save_json(alignment_res, cp_dir / "alignment_results.json")

        record = {
            "checkpoint_name": cp_dir.name,
            "model_type": model_type,
            "k": k,
            "training_time_sec": meta.get("training_time_sec", 0.0),
            "coherence_c_v": c_v,
            "coherence_u_mass": u_mass,
            "mean_semantic_similarity": alignment_res["mean_semantic_similarity"],
            "normalized_mutual_info": alignment_res["normalized_mutual_info"],
            "adjusted_rand_index": alignment_res["adjusted_rand_index"],
            "alignment_macro_f1": alignment_res["alignment_macro_f1"],
            "alignment_weighted_f1": alignment_res["alignment_weighted_f1"],
            "alignment_accuracy": alignment_res["alignment_accuracy"]
        }
        records.append(record)

    leaderboard_df = pd.DataFrame(records)

    # 4. Compute Composite Score for Joint Selection
    # Normalize c_v, NMI, and alignment_macro_f1 to [0, 1] range
    def min_max_norm(s: pd.Series) -> pd.Series:
        min_v, max_v = s.min(), s.max()
        if max_v == min_v:
            return pd.Series(1.0, index=s.index)
        return (s - min_v) / (max_v - min_v)

    norm_cv = min_max_norm(leaderboard_df["coherence_c_v"].fillna(0))
    norm_nmi = min_max_norm(leaderboard_df["normalized_mutual_info"].fillna(0))
    norm_f1 = min_max_norm(leaderboard_df["alignment_macro_f1"].fillna(0))
    norm_sim = min_max_norm(leaderboard_df["mean_semantic_similarity"].fillna(0))

    # Balanced composite: 40% Topic Coherence (Cv), 30% Semantic Alignment Sim, 30% Label Match F1/NMI
    leaderboard_df["composite_score"] = (
        0.40 * norm_cv +
        0.30 * norm_sim +
        0.15 * norm_nmi +
        0.15 * norm_f1
    )

    # Sort descending by composite score
    leaderboard_df = leaderboard_df.sort_values(by="composite_score", ascending=False).reset_index(drop=True)
    leaderboard_df["rank"] = leaderboard_df.index + 1

    # 5. Export Leaderboard and Plots
    out_csv = ensure_dir(paths_cfg.get("leaderboard_file", "reports/model_leaderboard.csv"))
    leaderboard_df.to_csv(out_csv, index=False)
    logger.info(f"Exported model leaderboard to: {out_csv}")

    # Generate Coherence Plots
    figures_dir = paths_cfg.get("figures_dir", "reports/figures")
    plot_coherence_curves(leaderboard_df, output_path=f"{figures_dir}/coherence_curves.png")

    return leaderboard_df


if __name__ == "__main__":
    build_leaderboard()
