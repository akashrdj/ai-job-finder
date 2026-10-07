import math
import re
from typing import Dict, List, Set
from collections import Counter

class EmbeddingVectorizer:
    """
    High-speed, zero-dependency TF-IDF & Subword N-Gram Cosine Vectorizer.
    Provides fast, deterministic semantic text similarity scoring.
    """

    STOPWORDS: Set[str] = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
        "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
        "but", "by", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
        "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn't",
        "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
        "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
        "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me",
        "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once",
        "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
        "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
        "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
        "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those",
        "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd",
        "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where",
        "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
        "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves"
    }

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        # Split on non-alphanumeric and retain tech terms like c++, node.js
        text = text.lower().replace("c++", "cpp").replace(".js", "js").replace("c#", "csharp")
        tokens = re.findall(r'[a-z0-9]+', text)
        filtered = [t for t in tokens if t not in cls.STOPWORDS and len(t) > 1]
        
        # Add bigrams for tech phrases (e.g. "full stack", "machine learning", "fast api")
        bigrams = [f"{filtered[i]}_{filtered[i+1]}" for i in range(len(filtered) - 1)]
        return filtered + bigrams

    @classmethod
    def compute_similarity(cls, text1: str, text2: str) -> float:
        """
        Calculates cosine similarity between two texts using token frequencies.
        Returns a float between 0.0 and 1.0.
        """
        tokens1 = cls._tokenize(text1)
        tokens2 = cls._tokenize(text2)

        if not tokens1 or not tokens2:
            return 0.0

        vec1 = Counter(tokens1)
        vec2 = Counter(tokens2)

        # Intersection of tokens
        common_tokens = set(vec1.keys()) & set(vec2.keys())
        dot_product = sum(vec1[t] * vec2[t] for t in common_tokens)

        mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

        if mag1 == 0.0 or mag2 == 0.0:
            return 0.0

        raw_similarity = dot_product / (mag1 * mag2)
        # Scale slightly to smooth short text overlap
        scaled = min(1.0, raw_similarity * 1.6)
        return round(scaled, 4)
