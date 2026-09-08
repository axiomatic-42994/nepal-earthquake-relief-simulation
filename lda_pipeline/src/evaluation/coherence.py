"""
Topic coherence computation (C_v and U_mass) using Gensim CoherenceModel.
"""
from typing import List, Dict, Any, Optional
from gensim.corpora import Dictionary
from gensim.models.coherencemodel import CoherenceModel

from ..utils.io import get_logger

logger = get_logger("evaluation.coherence")


def compute_topic_coherence(
    topic_words: List[List[str]],
    texts: List[List[str]],
    dictionary: Dictionary,
    corpus: Optional[List[List[Any]]] = None,
    top_n: int = 10
) -> Dict[str, float]:
    """
    Compute C_v and U_mass topic coherence for a list of topics (lists of term strings).
    """
    # Truncate topic words to top_n
    truncated_topics = [words[:top_n] for words in topic_words]

    scores = {}

    # 1. C_v Coherence (requires texts and dictionary)
    try:
        cm_cv = CoherenceModel(
            topics=truncated_topics,
            texts=texts,
            dictionary=dictionary,
            coherence="c_v",
            processes=1
        )
        scores["c_v"] = float(cm_cv.get_coherence())
    except Exception as e:
        logger.warning(f"Failed to compute C_v coherence: {e}")
        scores["c_v"] = float("nan")

    # 2. U_mass Coherence (requires corpus or dictionary)
    try:
        cm_umass = CoherenceModel(
            topics=truncated_topics,
            corpus=corpus,
            dictionary=dictionary,
            coherence="u_mass",
            processes=1
        )
        scores["u_mass"] = float(cm_umass.get_coherence())
    except Exception as e:
        logger.warning(f"Failed to compute U_mass coherence: {e}")
        scores["u_mass"] = float("nan")

    return scores
