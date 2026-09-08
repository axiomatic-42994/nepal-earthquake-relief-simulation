"""
Ground-truth alignment evaluation: maps unsupervised discovered topics to human-annotated
humanitarian class labels via semantic embedding cosine similarity, and computes
correspondence metrics (F1, ARI, NMI, confusion matrix).
"""
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, adjusted_rand_score, normalized_mutual_info_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

from ..utils.io import get_logger

logger = get_logger("evaluation.ground_truth")

_MODEL_CACHE = None


def compute_semantic_embeddings(texts: List[str], model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> np.ndarray:
    """
    Generate dense semantic embeddings using sentence-transformers with TF-IDF fallback.
    """
    global _MODEL_CACHE
    try:
        if _MODEL_CACHE is None:
            from sentence_transformers import SentenceTransformer
            _MODEL_CACHE = SentenceTransformer(model_name)
        embeddings = _MODEL_CACHE.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings
    except Exception as e:
        logger.warning(f"SentenceTransformer embedding failed ({e}), falling back to TF-IDF vectorizer.")
        tfidf = TfidfVectorizer(max_features=5000)
        return tfidf.fit_transform(texts).toarray()


def evaluate_ground_truth_alignment(
    topic_top_words: Dict[str, List[str]],
    doc_dominant_topics: List[int],
    ground_truth_labels: List[str],
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
) -> Dict[str, Any]:
    """
    Evaluate how well discovered topics align with human-annotated ground-truth class labels.
    """
    unique_labels = sorted(list(set(ground_truth_labels)))
    topic_keys = sorted(list(topic_top_words.keys()), key=lambda x: int(x.split("_")[-1]))
    num_topics = len(topic_keys)

    # 1. Represent each topic as a string of top-N terms
    topic_strings = [" ".join(topic_top_words[tk][:10]) for tk in topic_keys]
    
    # Formulate meaningful label descriptions (expand underscores/hyphens)
    label_strings = [label.replace("_", " ").replace("-", " ") for label in unique_labels]

    # 2. Compute semantic embeddings and cosine similarity matrix
    topic_embs = compute_semantic_embeddings(topic_strings, model_name=embedding_model_name)
    label_embs = compute_semantic_embeddings(label_strings, model_name=embedding_model_name)

    sim_matrix = cosine_similarity(topic_embs, label_embs)
    sim_df = pd.DataFrame(sim_matrix, index=topic_keys, columns=unique_labels)

    # 3. Map each topic to the most similar ground truth category
    topic_to_label_map = {}
    topic_to_sim_score = {}
    for idx, tk in enumerate(topic_keys):
        best_label_idx = np.argmax(sim_matrix[idx])
        best_label = unique_labels[best_label_idx]
        topic_to_label_map[idx] = best_label
        topic_to_sim_score[tk] = float(sim_matrix[idx, best_label_idx])

    # 4. Map document dominant topics to predicted labels
    predicted_labels = [topic_to_label_map.get(top_idx, "unknown") for top_idx in doc_dominant_topics]

    # 5. Compute Alignment Metrics
    ari = float(adjusted_rand_score(ground_truth_labels, doc_dominant_topics))
    nmi = float(normalized_mutual_info_score(ground_truth_labels, doc_dominant_topics))
    mean_cosine_sim = float(np.mean(list(topic_to_sim_score.values())))

    # Generate classification report
    report = classification_report(
        ground_truth_labels,
        predicted_labels,
        labels=unique_labels,
        zero_division=0,
        output_dict=True
    )
    macro_f1 = float(report["macro avg"]["f1-score"])
    weighted_f1 = float(report["weighted avg"]["f1-score"])
    accuracy = float(report["accuracy"])

    # Contingency / Confusion Matrix DataFrame
    contingency_df = pd.crosstab(
        pd.Series(predicted_labels, name="Predicted Class (from Topic)"),
        pd.Series(ground_truth_labels, name="Actual Class Label"),
        dropna=False
    )

    results = {
        "mean_semantic_similarity": mean_cosine_sim,
        "adjusted_rand_index": ari,
        "normalized_mutual_info": nmi,
        "alignment_accuracy": accuracy,
        "alignment_macro_f1": macro_f1,
        "alignment_weighted_f1": weighted_f1,
        "topic_to_label_mapping": {tk: topic_to_label_map[int(tk.split("_")[-1])] for tk in topic_keys},
        "topic_similarity_scores": topic_to_sim_score,
        "similarity_matrix": sim_df.to_dict(),
        "confusion_matrix": contingency_df.to_dict()
    }

    logger.info(
        f"Alignment Results: Mean Cosine Sim={mean_cosine_sim:.3f}, "
        f"NMI={nmi:.3f}, ARI={ari:.3f}, Macro-F1={macro_f1:.3f}"
    )

    return results
