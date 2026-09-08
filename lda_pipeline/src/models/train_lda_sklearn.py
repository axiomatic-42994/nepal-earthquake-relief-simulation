"""
Trainer for Scikit-Learn Latent Dirichlet Allocation (Online / Batch variational Bayes).
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.decomposition import LatentDirichletAllocation
from gensim.corpora import Dictionary
from gensim.matutils import corpus2csc

from ..utils.io import ensure_dir, save_json, save_pickle, get_logger

logger = get_logger("models.sklearn_lda")


def train_sklearn_lda(
    corpus: List[List[Tuple[int, int]]],
    dictionary: Dictionary,
    num_topics: int,
    max_iter: int = 20,
    learning_method: str = "batch",
    random_state: int = 42,
    checkpoint_dir: Optional[str] = None
) -> Tuple[LatentDirichletAllocation, Dict[str, Any]]:
    """
    Train Scikit-Learn LDA on BoW matrix and return model + metadata.
    """
    model_name = "sklearn_lda"
    logger.info(f"Converting Gensim BoW to Scipy CSR matrix (K={num_topics})...")
    # gensim corpus2csc returns term-by-doc, transpose to doc-by-term for sklearn
    csc = corpus2csc(corpus, num_terms=len(dictionary))
    csr_doc_term = csc.T.tocsr()

    logger.info(f"Training Scikit-Learn LDA (K={num_topics}, max_iter={max_iter}, method={learning_method})...")
    start_time = time.time()

    model = LatentDirichletAllocation(
        n_components=num_topics,
        max_iter=max_iter,
        learning_method=learning_method,
        random_state=random_state,
        n_jobs=-1
    )
    model.fit(csr_doc_term)
    elapsed_sec = time.time() - start_time
    logger.info(f"Training completed in {elapsed_sec:.2f} seconds.")

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
        "learning_method": learning_method,
        "random_state": random_state,
        "num_docs": len(corpus),
        "vocab_size": len(dictionary),
        "topic_top_words": topic_words
    }

    if checkpoint_dir:
        model_save_dir = Path(checkpoint_dir) / f"{model_name}_k{num_topics}"
        ensure_dir(model_save_dir)
        save_pickle(model, model_save_dir / "model.pkl")
        save_json(metadata, model_save_dir / "metadata.json")
        logger.info(f"Saved model checkpoint to: {model_save_dir}")

    return model, metadata
