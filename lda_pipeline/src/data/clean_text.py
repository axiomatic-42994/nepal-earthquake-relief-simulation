"""
Text preprocessing and cleaning pipeline for disaster social media tweets.
"""
import re
import html
import unicodedata
from typing import List, Optional, Set, Union, Dict, Any
from pathlib import Path

import pandas as pd
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from gensim.models.phrases import Phrases, Phraser

from ..utils.io import load_config, ensure_dir, get_logger, save_pickle, load_pickle

logger = get_logger("data.clean")


def get_default_stopwords() -> Set[str]:
    """Retrieve standard English stopwords with NLTK download fallback."""
    try:
        sw = set(stopwords.words("english"))
    except LookupError:
        nltk.download("stopwords", quiet=True)
        sw = set(stopwords.words("english"))
    return sw


class TextCleaner:
    """
    Robust NLP cleaning pipeline tailored for crisis informatics:
    1. Sanitizes URLs, @mentions, hashtag symbols, HTML entities, RT prefixes, special chars.
    2. Tokenizes & lemmatizes (WordNetLemmatizer or spaCy).
    3. Removes standard + disaster domain stopwords.
    4. Learns and applies bigram / trigram phrase modeling.
    """

    def __init__(
        self,
        custom_stopwords: Optional[List[str]] = None,
        min_token_len: int = 3,
        max_token_len: int = 25,
        min_phrase_count: int = 5,
        phrase_threshold: float = 10.0
    ):
        self.min_token_len = min_token_len
        self.max_token_len = max_token_len
        self.min_phrase_count = min_phrase_count
        self.phrase_threshold = phrase_threshold

        # Initialize base stopwords
        self.stopwords = get_default_stopwords()
        if custom_stopwords:
            self.stopwords.update([w.lower().strip() for w in custom_stopwords])

        # Initialize Lemmatizer
        try:
            self.lemmatizer = WordNetLemmatizer()
            # Test lemmatizer to trigger download if missing
            self.lemmatizer.lemmatize("running", pos="v")
        except LookupError:
            nltk.download("wordnet", quiet=True)
            nltk.download("omw-1.4", quiet=True)
            self.lemmatizer = WordNetLemmatizer()

        # Bigram & Trigram phrasers
        self.bigram_phraser: Optional[Phraser] = None
        self.trigram_phraser: Optional[Phraser] = None

        # Compile regex patterns
        self.url_pattern = re.compile(r"https?://\S+|www\.\S+|bit\.ly/\S+", re.IGNORECASE)
        self.mention_pattern = re.compile(r"@\w+")
        self.rt_pattern = re.compile(r"^(rt\s*:?|rt\s*@\w+:?)", re.IGNORECASE)
        self.hashtag_pattern = re.compile(r"#(\w+)")
        self.non_ascii_pattern = re.compile(r"[^\x00-\x7F]+")
        self.punct_pattern = re.compile(r"[^a-zA-Z\s]")

    def clean_raw_text(self, text: str) -> str:
        """Sanitize raw string: remove URLs, mentions, RTs, unpack hashtags, unescape HTML."""
        if not isinstance(text, str):
            return ""

        # Unescape HTML entities (&amp; -> &, &gt; -> >, etc.)
        text = html.unescape(text)

        # Normalize unicode
        text = unicodedata.normalize("NFKD", text)

        # Strip Retweet prefix
        text = self.rt_pattern.sub(" ", text)

        # Remove URLs
        text = self.url_pattern.sub(" ", text)

        # Remove @mentions
        text = self.mention_pattern.sub(" ", text)

        # Transform hashtags: #kathmandu -> kathmandu
        text = self.hashtag_pattern.sub(r" \1 ", text)

        # Strip non-ASCII characters
        text = self.non_ascii_pattern.sub(" ", text)

        # Replace numbers and punctuation with spaces
        text = self.punct_pattern.sub(" ", text)

        # Lowercase and collapse multiple whitespaces
        text = " ".join(text.lower().split())

        return text

    def tokenize_and_lemmatize(self, text: str) -> List[str]:
        """Convert cleaned string into a list of lemmatized, stopword-filtered tokens."""
        cleaned_text = self.clean_raw_text(text)
        tokens = cleaned_text.split()
        
        valid_tokens = []
        for token in tokens:
            if len(token) < self.min_token_len or len(token) > self.max_token_len:
                continue
            if token in self.stopwords:
                continue
            
            # Lemmatize noun then verb
            lemma = self.lemmatizer.lemmatize(token, pos="n")
            lemma = self.lemmatizer.lemmatize(lemma, pos="v")

            if lemma not in self.stopwords and len(lemma) >= self.min_token_len:
                valid_tokens.append(lemma)

        return valid_tokens

    def fit_phrasers(self, tokenized_docs: List[List[str]]) -> None:
        """Learn bigram and trigram collocations from corpus tokens."""
        logger.info("Fitting bigram collocation model...")
        bigram_model = Phrases(
            tokenized_docs,
            min_count=self.min_phrase_count,
            threshold=self.phrase_threshold
        )
        self.bigram_phraser = Phraser(bigram_model)

        logger.info("Fitting trigram collocation model...")
        trigram_docs = [self.bigram_phraser[doc] for doc in tokenized_docs]
        trigram_model = Phrases(
            trigram_docs,
            min_count=self.min_phrase_count,
            threshold=self.phrase_threshold
        )
        self.trigram_phraser = Phraser(trigram_model)
        logger.info("Phrasers fitted successfully.")

    def apply_phrases(self, tokens: List[str]) -> List[str]:
        """Apply learned bigrams and trigrams to token list."""
        if self.bigram_phraser is None or self.trigram_phraser is None:
            return tokens
        bigrams = self.bigram_phraser[tokens]
        return self.trigram_phraser[bigrams]

    def transform_corpus(self, texts: List[str], fit_phrases: bool = True) -> List[List[str]]:
        """Clean, tokenize, lemmatize, and phrase-model a full corpus of texts."""
        logger.info(f"Tokenizing and lemmatizing {len(texts):,} documents...")
        tokenized = [self.tokenize_and_lemmatize(t) for t in texts]

        if fit_phrases:
            self.fit_phrasers(tokenized)

        if self.bigram_phraser is not None:
            logger.info("Applying bigram and trigram transforms...")
            tokenized = [self.apply_phrases(doc) for doc in tokenized]

        return tokenized

    def save(self, filepath: Union[str, Path]) -> None:
        """Serialize cleaner state (phrasers & configuration)."""
        save_pickle(self, filepath)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "TextCleaner":
        """Deserialize cleaner state."""
        return load_pickle(filepath)
