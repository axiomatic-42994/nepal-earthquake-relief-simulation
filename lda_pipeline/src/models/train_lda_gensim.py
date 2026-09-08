"""
Trainer for Gensim Latent Dirichlet Allocation (Variational Bayes & Multicore).
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from gensim.corpora import Dictionary
from gensim.models import LdaModel, LdaMulticore

from ..utils.io import ensure_dir, save_json, get_logger

logger = get_logger("models.gensim_lda")


def train_gensim_lda(
    corpus: List[List[Tuple[int, int]]],
    dictionary: Dictionary,
    num_topics: int,
    use_multicore: bool = False,
    passes: int = 15,
    iterations: int = 200,
    alpha: str = "auto",
    eta: str = "auto",
    random_state: int = 42,
    checkpoint_dir: Optional[str] = None
) -> Tuple[Any, Dict[str, Any]]:
    """
    Train Gensim LDA model on bag-of-words corpus and return model + metadata.
    """
    model_name = "gensim_lda_multicore" if use_multicore else "gensim_lda"
    logger.info(f"Training {model_name} with K={num_topics} (passes={passes}, iterations={iterations})...")
    start_time = time.time()

    if use_multicore:
        # Multicore does not support auto alpha in some versions, fallback to symmetric
        alpha_param = "symmetric" if alpha == "auto" else alpha
        model = LdaMulticore(
            corpus=corpus,
            id2word=dictionary,
            num_topics=num_topics,
            passes=passes,
            iterations=iterations,
            alpha=alpha_param,
            eta=eta,
            random_state=random_state
        )
    else:
        model = LdaModel(
            corpus=corpus,
            id2word=dictionary,
            num_topics=num_topics,
            passes=passes,
            iterations=iterations,
            alpha=alpha,
            eta=eta,
            random_state=random_state,
            eval_every=None
        )

    elapsed_sec = time.time() - start_time
    logger.info(f"Training completed in {elapsed_sec:.2f} seconds.")

    # Extract top terms per topic
    topic_words = {}
    for topic_id in range(num_topics):
        top_terms = [word for word, _ in model.show_topic(topic_id, topn=15)]
        topic_words[f"topic_{topic_id}"] = top_terms

    metadata = {
        "model_type": model_name,
        "k": num_topics,
        "training_time_sec": elapsed_sec,
        "passes": passes,
        "iterations": iterations,
        "alpha": str(alpha),
        "eta": str(eta),
        "random_state": random_state,
        "num_docs": len(corpus),
        "vocab_size": len(dictionary),
        "topic_top_words": topic_words
    }

    # Save checkpoint if requested
    if checkpoint_dir:
        model_save_dir = Path(checkpoint_dir) / f"{model_name}_k{num_topics}"
        ensure_dir(model_save_dir)
        model_path = model_save_dir / "model.gensim"
        model.save(str(model_path))
        meta_path = model_save_dir / "metadata.json"
        save_json(metadata, meta_path)
        logger.info(f"Saved model checkpoint to: {model_save_dir}")

    return model, metadata
