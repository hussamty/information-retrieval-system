# core/text_preprocessor.py

import re
import string
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk import pos_tag, ne_chunk
from nltk.tree import Tree

# Note: NLTK downloads are handled in the previous version.

class TextPreprocessor:
    """
    An enhanced preprocessor that separates base processing (lemmatization)
    from advanced feature extraction (NER).
    """
    def __init__(self):
        self.stop_words = set(stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()

    def _get_wordnet_pos(self, tag_parameter):
        """Map POS tag to first character lemmatize() accepts"""
        tag = tag_parameter[0].upper()
        tag_dict = {"J": "a", "N": "n", "V": "v", "R": "r"}
        return tag_dict.get(tag, 'n')

    def preprocess(self, text):
        """
        Applies base preprocessing: Lemmatization only. This is fast and
        maintains better semantic integrity than stemming.
        """
        text = text.lower()
        tokens = word_tokenize(text)
        pos_tags = pos_tag(tokens)

        processed_tokens = []
        for word, tag in pos_tags:
            word = re.sub(r'[\d' + string.punctuation + ']', '', word)
            if not word: continue

            lemma = self.lemmatizer.lemmatize(word, self._get_wordnet_pos(tag))
            
            if lemma not in self.stop_words and len(lemma) > 2:
                processed_tokens.append(lemma)
        
        return " ".join(processed_tokens)

    def extract_entities(self, text):
        """
        Extracts Named Entities from a given text. This is a separate,
        CPU-intensive function to be called on-demand (e.g., for re-ranking).
        """
        entities = set()
        tokens = word_tokenize(text.lower())
        pos_tags = pos_tag(tokens)
        chunks = ne_chunk(pos_tags)

        for chunk in chunks:
            if isinstance(chunk, Tree):
                # It's a named entity, join the words and lemmatize
                for word, tag in chunk.leaves():
                     lemma = self.lemmatizer.lemmatize(word, self._get_wordnet_pos(tag))
                     if lemma not in self.stop_words and len(lemma) > 2:
                        entities.add(lemma)
        return entities

