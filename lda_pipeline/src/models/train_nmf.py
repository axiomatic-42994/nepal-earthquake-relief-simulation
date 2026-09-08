"""
Trainer for Scikit-Learn Non-Negative Matrix Factorization (NMF) Baseline.
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from sklearn.decomposition import NMF
from gensim.corpora import Dictionary
from gensim.matutils import corpus2csc

from ..utils.io import ensure_dir, save_json, save_pickle, get_logger

logger = get_logger("models.nmf")


def train_sklearn_nmf(
    corpus_tfidf: List[List[Tuple[int, float]]],
    dictionary: Dictionary,
    num_topics: int,
    max_iter: int = 200,
    init: str = "nndsvda",
    random_state: int = 42,
    checkpoint_dir: Optional[str] = None
) -> Tuple[NMF, Dict[str, Any]]:
    """
    Train Scikit-Learn NMF baseline on TF-IDF matrix and return model + metadata.
    """
    model_name = "sklearn_nmf"
    logger.info(f"Converting Gensim TF-IDF to Scipy CSR matrix (K={num_topics})...")
    csc = corpus2csc(corpus_tfidf, num_terms=len(dictionary))
    csr_doc_term = csc.T.tocsr()

    logger.info(f"Training Scikit-Learn NMF (K={num_topics}, max_iter={max_iter}, init={init})...")
    start_time = time.time()

    model = NMF(
        n_components=num_topics,
        max_iter=max_iter,
        init=init,
        random_state=random_state
    )
    model.fit(csr_doc_term)
    elapsed_sec = time.time() - start_time
    logger.info(f"NMF training completed in {elapsed_sec:.2f} seconds.")

    # Extract top terms
    feature_names = [dictionary[i] for i in range(len(dictionary))]
    topic_words = {}
    for topic_idx, topic in enumerate(model.components_):
        top_indices = topic.argsort()[:-16:-1]
        topic_words[f"topic_{topic_idx}"] = [feature_names[i] for i in top_indices]

    metadata = {
        "model_type": model_name,
        "k": num_topics,
        "training_time_sec": elapsed_sec,
        "max_iter": max_iter,
        "init": init,
        "random_state": random_state,
        "num_docs": len(corpus_tfidf),
        "vocab_size": len(dictionary),
        "topic_top_words": topic_words
    }

    if checkpoint_dir:
        model_save_dir = Path(checkpoint_dir) / f"{model_name}_k{num_topics}"
        ensure_dir(model_save_dir)
        save_pickle(model, model_save_dir / "model.pkl")
        save_json(metadata, model_save_dir / "metadata.json")
        logger.info(f"Saved NMF model checkpoint to: {model_save_dir}")

    return model, metadata
