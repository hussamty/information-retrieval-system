# core/text_preprocessor.py

# Import necessary libraries from NLTK (Natural Language Toolkit) and standard Python libraries
import re # For regular expressions, used here to remove punctuation and digits
import string # Contains a string of all punctuation characters
from nltk.tokenize import word_tokenize # For splitting text into individual words (tokens)
from nltk.corpus import stopwords # For getting a list of common English stop words (like 'the', 'a', 'is')
from nltk.stem import WordNetLemmatizer # For reducing words to their base or dictionary form (lemma)
from nltk import pos_tag, ne_chunk # For Part-of-Speech tagging and Named Entity Chunking
from nltk.tree import Tree # For working with the tree structure returned by ne_chunk


class TextPreprocessor:
    """
    An enhanced preprocessor that separates base processing (lemmatization)
    from advanced feature extraction (NER).
    """
    # The constructor method, called when a new TextPreprocessor object is created
    def __init__(self):
        # Load the set of English stop words for efficient lookup
        self.stop_words = set(stopwords.words('english'))
        # Create an instance of the WordNet Lemmatizer
        self.lemmatizer = WordNetLemmatizer()

    # A helper method to convert NLTK's POS tags to a format the lemmatizer understands
    def _get_wordnet_pos(self, tag_parameter):
        """Map POS tag to first character lemmatize() accepts"""
        # Get the first letter of the POS tag (e.g., 'NN' -> 'N') and make it uppercase
        tag = tag_parameter[0].upper()
        # A dictionary to map the first letter to the format required by WordNet ('a' for adjective, 'n' for noun, etc.)
        tag_dict = {"J": "a", "N": "n", "V": "v", "R": "r"}
        # Return the corresponding value, or 'n' (noun) by default if the tag is not found
        return tag_dict.get(tag, 'n')

    # The main method for basic text cleaning and preprocessing
    def preprocess(self, text):
        """
        Applies base preprocessing: Lemmatization only. This is fast and
        maintains better semantic integrity than stemming.
        """
        # Convert the entire text to lowercase
        text = text.lower()
        # Tokenize the text into a list of words
        tokens = word_tokenize(text)
        # Get the Part-of-Speech tag for each token (e.g., [('running', 'VBG'), ('is', 'VBZ'), ('fun', 'NN')])
        pos_tags = pos_tag(tokens)

        # Initialize an empty list to store the processed tokens
        processed_tokens = []
        # Loop through each word and its corresponding POS tag
        for word, tag in pos_tags:
            # Use a regular expression to remove all digits and punctuation from the word
            word = re.sub(r'[\d' + string.punctuation + ']', '', word)
            # If the word is empty after cleaning (e.g., it was just a number), skip it
            if not word: continue

            # Lemmatize the word, using the POS tag to be more accurate (e.g., 'running' (verb) -> 'run')
            lemma = self.lemmatizer.lemmatize(word, self._get_wordnet_pos(tag))
            
            # Keep the lemma if it's not a stop word and has a length greater than 2
            if lemma not in self.stop_words and len(lemma) > 2:
                processed_tokens.append(lemma)
        
        # Join the processed tokens back into a single string, separated by spaces
        return " ".join(processed_tokens)

    # A separate method for extracting Named Entities (like persons, organizations, locations)
    def extract_entities(self, text):
        """
        Extracts Named Entities from a given text. This is a separate,
        CPU-intensive function to be called on-demand (e.g., for re-ranking).
        """
        # Use a set to store entities to automatically handle duplicates
        entities = set()
        # Tokenize the lowercased text
        tokens = word_tokenize(text.lower())
        # Get POS tags for the tokens
        pos_tags = pos_tag(tokens)
        # Perform Named Entity Chunking, which groups tokens into entities
        chunks = ne_chunk(pos_tags)

        # Iterate through the chunks created by ne_chunk
        for chunk in chunks:
            # If the chunk is a Tree, it's a named entity
            if isinstance(chunk, Tree):
                # Iterate through the leaves (words/tags) of the entity tree
                for word, tag in chunk.leaves():
                     # Lemmatize the word from the entity
                     lemma = self.lemmatizer.lemmatize(word, self._get_wordnet_pos(tag))
                     # Add the lemmatized entity word to the set if it's not a stop word and is long enough
                     if lemma not in self.stop_words and len(lemma) > 2:
                        entities.add(lemma)
        # Return the set of unique, cleaned entities
        return entities

