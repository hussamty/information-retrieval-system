# Import necessary libraries
from fastapi import FastAPI, HTTPException # For creating the API and handling errors
from pydantic import BaseModel, Field # For defining data models and adding extra info to fields
from typing import List # For type hinting lists
import os # For interacting with the file system
import joblib # For loading saved models
import json # For loading the inverted index
import numpy as np # For numerical operations
from sklearn.metrics.pairwise import cosine_similarity # To calculate similarity for TF-IDF
from sentence_transformers import SentenceTransformer # To load the BERT model for encoding queries
import faiss # To perform fast similarity search on embeddings
import mysql.connector # To connect to the database to fetch document text

# Import custom modules
from core.text_preprocessor import TextPreprocessor # Our text processing class
from config import MODELS_DIR, EMBEDDING_MODEL_NAME, DB_CONFIG # Import constants and configuration
from spellchecker import SpellChecker # For spelling correction


# --- Define the structure for API requests and responses ---

# The structure for a search request
class SearchRequest(BaseModel):
    dataset_name: str
    query: str
    # The type of search model to use, with 'hybrid' as the default
    model_type: str = Field("hybrid", description="'tfidf', 'bm25', 'bert', or 'hybrid'")
    # The number of top results to return
    top_k: int = 10
    # BM25 parameters, can be tuned
    k1: float = 1.6
    b: float = 0.75
    # A flag to enable or disable re-ranking based on Named Entity Recognition (NER)
    enable_ner_reranking: bool = False
    # The weight to give the BM25 score in the hybrid model
    hybrid_bm25_weight: float = 0.8
    # A flag to enable or disable cluster-based re-ranking
    enable_cluster_reranking: bool = False

# The structure for a single search result
class SearchResult(BaseModel):
    doc_id: str
    score: float
    cluster_id: int = -1 # -1 indicates no cluster information

# The structure for the final search response, containing a list of results
class SearchResponse(BaseModel):
    results: List[SearchResult]

# --- Initialize the FastAPI application ---
app = FastAPI(
    title="Advanced Search API with Suggestion",
    description="الخدمة المركزية للبحث، مع ميزات إعادة الترتيب بـ NER، الدمج الموزون، واقتراح الاستعلامات."
)

# --- The main class that encapsulates all search functionality ---
class SearchService:
    # The constructor, called when an instance of the class is created
    def __init__(self):
        # Initialize our text preprocessor
        self.preprocessor = TextPreprocessor()
        # A cache to store loaded models to avoid reloading them for every request
        self.loaded_models = {}
        # A cache to store fetched document texts to avoid repeated database calls
        self.doc_text_cache = {}
        # Initialize the spell checker for English
        self.spell_checker = SpellChecker(language='en')

    # A helper method to log a query into the database
    def _log_query(self, dataset_name: str, query_text: str, successful: bool):
        try:
            cnx = self._get_db_connection()
            cursor = cnx.cursor()
            sql = "INSERT INTO query_logs (dataset_name, query_text, successful) VALUES (%s, %s, %s)"
            cursor.execute(sql, (dataset_name, query_text, successful))
            cnx.commit()
            cursor.close()
            cnx.close()
        except mysql.connector.Error as err:
            # It's okay to fail silently here, as logging is not critical
            print(f"Failed to log query: {err}", flush=True)

    # A helper method to get a new database connection
    def _get_db_connection(self):
        return mysql.connector.connect(**DB_CONFIG)

    # A method to fetch the original text of documents from the database
    def _fetch_original_texts(self, doc_ids, dataset_name):
        texts, ids_to_fetch = {}, []
        # First, check the cache for any documents we've already fetched
        for doc_id in doc_ids:
            if doc_id in self.doc_text_cache:
                texts[doc_id] = self.doc_text_cache[doc_id]
            else:
                ids_to_fetch.append(doc_id)
        # If there are any document IDs we haven't seen before, fetch them from the DB
        if ids_to_fetch:
            try:
                cnx = self._get_db_connection()
                cursor = cnx.cursor(dictionary=True) # `dictionary=True` returns rows as dicts
                # Create a string of placeholders (%s) for the SQL IN clause
                placeholders = ', '.join(['%s'] * len(ids_to_fetch))
                sql = f"SELECT doc_id, original_text FROM documents WHERE doc_id IN ({placeholders}) AND dataset = %s"
                params = ids_to_fetch + [dataset_name] # Combine the IDs and dataset name for the query
                cursor.execute(sql, params)
                # For each row returned, add the text to our cache and the results dictionary
                for row in cursor.fetchall():
                    self.doc_text_cache[row['doc_id']] = row['original_text']
                    texts[row['doc_id']] = row['original_text']
                cursor.close(); cnx.close()
            except mysql.connector.Error: pass # Ignore database errors for now
        return texts

    # A method to load all necessary models for a given dataset
    def _load_models(self, dataset_name):
        # If models for this dataset are already in our cache, return them immediately
        if dataset_name in self.loaded_models: return self.loaded_models[dataset_name]
        # Sanitize the name and construct the path to the model directory
        sanitized_name = dataset_name.replace('/', '_')
        model_dir = os.path.join(MODELS_DIR, sanitized_name)
        # If the directory doesn't exist, the models haven't been built yet, so raise an error
        if not os.path.exists(model_dir): raise HTTPException(status_code=404, detail=f"Models not found for {dataset_name}.")
        # Load all the model files from disk
        with open(os.path.join(model_dir, 'inverted_index.json'), 'r') as f: inverted_index = json.load(f)
        models = {
            'inverted_index': inverted_index,
            'tfidf_vectorizer': joblib.load(os.path.join(model_dir, 'tfidf_vectorizer.joblib')),
            'tfidf_matrix': joblib.load(os.path.join(model_dir, 'tfidf_matrix.joblib')),
            'bm25_model': joblib.load(os.path.join(model_dir, 'bm25_model.joblib')),
            'doc_ids': joblib.load(os.path.join(model_dir, 'doc_ids.joblib')),
            'bert_model': SentenceTransformer(EMBEDDING_MODEL_NAME),
            'faiss_index': faiss.read_index(os.path.join(model_dir, 'faiss.index'))
        }
        # Create a mapping from document ID to its index for quick lookups
        models['doc_id_to_idx'] = {doc_id: i for i, doc_id in enumerate(models['doc_ids'])}
        # Load cluster information if it exists
        cluster_path = os.path.join(model_dir, 'clusters.joblib')
        if os.path.exists(cluster_path):
            models['clusters'] = joblib.load(cluster_path)
            models['doc_id_to_cluster'] = {doc_id: cluster for doc_id, cluster in zip(models['doc_ids'], models['clusters'])}
        else:
            models['clusters'] = None
            models['doc_id_to_cluster'] = {}

        # Store the loaded models in the cache
        self.loaded_models[dataset_name] = models
        return models

    # Search method using TF-IDF
    def _search_tfidf(self, query, models, k):
        query_terms, candidate_docs_set = query.split(), set()
        # Use the inverted index to get a set of candidate documents that contain at least one query term
        for term in query_terms:
            if term in models['inverted_index']: candidate_docs_set.update(models['inverted_index'][term])
        if not candidate_docs_set: return [] # If no candidates, return empty list
        candidate_doc_ids = list(candidate_docs_set)
        # Get the numerical indices of the candidate documents
        candidate_indices = [models['doc_id_to_idx'][doc_id] for doc_id in candidate_doc_ids if doc_id in models['doc_id_to_idx']]
        if not candidate_indices: return []
        # Transform the query into a TF-IDF vector
        query_vec = models['tfidf_vectorizer'].transform([query])
        # Get the TF-IDF vectors for only the candidate documents
        candidate_matrix = models['tfidf_matrix'][candidate_indices]
        # Calculate cosine similarity between the query vector and all candidate vectors
        scores = cosine_similarity(query_vec, candidate_matrix).flatten()
        # Combine the document IDs with their scores
        scored_candidates = zip([candidate_doc_ids[i] for i in range(len(candidate_indices))], scores)
        # Sort the results by score in descending order
        sorted_results = sorted(scored_candidates, key=lambda item: item[1], reverse=True)
        # Return the top k results, formatted as a list of dictionaries
        return [{'doc_id': doc_id, 'score': float(score)} for doc_id, score in sorted_results[:k] if score > 0]
    
    # Search method using BM25
    def _search_bm25(self, query, models, k, k1, b):
        # Set the BM25 parameters k1 and b
        models['bm25_model'].k1 = k1; models['bm25_model'].b = b
        # Get scores for all documents in the corpus
        scores = models['bm25_model'].get_scores(query.split())
        # Get the indices of the top k scores
        indices = np.argsort(scores)[-k:][::-1]
        # Return the top k results with their scores
        return [{'doc_id': models['doc_ids'][i], 'score': float(scores[i])} for i in indices if scores[i] > 0]

    # Search method using BERT and FAISS
    def _search_bert(self, query, models, k):
        # Encode the query into a BERT embedding
        query_embedding = models['bert_model'].encode([query]).astype('float32')
        # Search the FAISS index for the k nearest neighbors to the query embedding
        distances, indices = models['faiss_index'].search(query_embedding, k)
        # Convert distances to similarity scores (a simple conversion)
        scores = 1 / (1 + distances[0])
        # Return the top k results with their scores
        return [{'doc_id': models['doc_ids'][i], 'score': float(scores[idx])} for idx, i in enumerate(indices[0])]

    # Search method that combines BM25 and BERT scores
    def _search_hybrid_weighted_sum(self, processed_query, original_query, models, k, k1, b, bm25_weight):
        # Get results from both BM25 and BERT
        bm25_res = self._search_bm25(processed_query, models, k, k1, b)
        bert_res = self._search_bert(original_query, models, k)
        # Create dictionaries mapping doc_id to score for easy lookup
        bm25_scores = {res['doc_id']: res['score'] for res in bm25_res}
        bert_scores = {res['doc_id']: res['score'] for res in bert_res}
        # A helper function to normalize scores to a 0-1 range (Min-Max scaling)
        def normalize(scores_dict):
            if not scores_dict: return {}
            scores = list(scores_dict.values())
            min_score, max_score = min(scores), max(scores)
            if max_score == min_score: return {doc_id: 1.0 for doc_id in scores_dict}
            return {doc_id: (score - min_score) / (max_score - min_score) for doc_id, score in scores_dict.items()}
        # Normalize the scores from both models
        norm_bm25 = normalize(bm25_scores)
        norm_bert = normalize(bert_scores)
        # Combine the scores using a weighted sum
        final_scores = {}
        all_ids = set(norm_bm25.keys()).union(set(norm_bert.keys())) # Get all unique doc IDs from both results
        bert_weight = 1 - bm25_weight
        for doc_id in all_ids:
            score1 = norm_bm25.get(doc_id, 0) # Get BM25 score, default to 0 if not present
            score2 = norm_bert.get(doc_id, 0) # Get BERT score, default to 0 if not present
            final_scores[doc_id] = (bm25_weight * score1) + (bert_weight * score2)
        # Sort the combined scores
        sorted_docs = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)
        # Return the top k hybrid results
        return [{'doc_id': doc_id, 'score': score} for doc_id, score in sorted_docs[:k]]

    # The main public search method that orchestrates the entire process
    def search(self, req: SearchRequest):
        # Load the necessary models for the requested dataset
        models = self._load_models(req.dataset_name)
        # Preprocess the user's query
        processed_query = self.preprocessor.preprocess(req.query)
        # If NER re-ranking is enabled, fetch more initial results to re-rank from
        initial_retrieval_size = 50 if req.enable_ner_reranking else req.top_k
        
        # A map to call the correct search function based on model_type
        base_model_map = {
            'tfidf': lambda: self._search_tfidf(processed_query, models, initial_retrieval_size),
            'bm25': lambda: self._search_bm25(processed_query, models, initial_retrieval_size, req.k1, req.b),
            'bert': lambda: self._search_bert(req.query, models, initial_retrieval_size),
            'hybrid': lambda: self._search_hybrid_weighted_sum(
                processed_query, req.query, models, initial_retrieval_size,
                req.k1, req.b, req.hybrid_bm25_weight
            )
        }
        if req.model_type not in base_model_map: raise HTTPException(status_code=400, detail="Invalid model_type")
        # Get the initial search results
        initial_results = base_model_map[req.model_type]()

        # Log the query
        self._log_query(req.dataset_name, req.query, successful=bool(initial_results))

        # Add cluster_id to the initial results
        for res in initial_results:
            res['cluster_id'] = int(models.get('doc_id_to_cluster', {}).get(res['doc_id'], -1))

        # --- Cluster Re-ranking Logic ---
        if req.enable_cluster_reranking and models.get('clusters') is not None:
            print("[SEARCH] Applying cluster-based re-ranking.", flush=True)
            # Determine if the model used for search is BERT-based
            use_bert_for_clustering = req.model_type in ['bert', 'hybrid']
            results_to_process = self._rerank_by_cluster(req.query, initial_results, models, use_bert_for_clustering)
        else:
            results_to_process = initial_results

        # If we have no results, or if NER re-ranking is disabled, return the current results
        if not results_to_process or not req.enable_ner_reranking:
            return results_to_process[:req.top_k]

        # --- NER Re-ranking Logic ---
        print("[SEARCH] Applying NER-based re-ranking.", flush=True)
        query_entities = self.preprocessor.extract_entities(req.query)
        if not query_entities:
            return results_to_process[:req.top_k]

        candidate_ids = [res['doc_id'] for res in results_to_process]
        candidate_texts = self._fetch_original_texts(candidate_ids, req.dataset_name)
        
        reranked_results = []
        ner_bonus = 0.5
        for result in results_to_process:
            doc_id, original_score, cluster_id = result['doc_id'], result['score'], result.get('cluster_id', -1)
            doc_text = candidate_texts.get(doc_id, "")
            doc_entities = self.preprocessor.extract_entities(doc_text)
            matching_entities_count = len(query_entities.intersection(doc_entities))
            final_score = original_score + (matching_entities_count * ner_bonus)
            reranked_results.append({'doc_id': doc_id, 'score': final_score, 'cluster_id': cluster_id})
            
        reranked_results.sort(key=lambda x: x['score'], reverse=True)
        return reranked_results[:req.top_k]

    # --- Method for cluster-based re-ranking ---
    def _rerank_by_cluster(self, query, results, models, use_bert):
        if not models.get('clusters') is not None:
            return results # No cluster information available

        # Determine the query's cluster
        if use_bert:
            query_embedding = models['bert_model'].encode([query]).astype('float32')
            # This is a simplification; in a real system, you'd use the kmeans model to predict
            # For now, we find the closest document in the original results and use its cluster
            if not results:
                return results
            closest_doc_id = results[0]['doc_id']
            query_cluster = models['doc_id_to_cluster'].get(closest_doc_id, -1)
        else:
            # For TF-IDF, we can transform the query and predict the cluster
            # This requires the kmeans model to be loaded, which is not done here for simplicity.
            # As a fallback, we use the cluster of the top result.
            if not results:
                return results
            closest_doc_id = results[0]['doc_id']
            query_cluster = models['doc_id_to_cluster'].get(closest_doc_id, -1)

        if query_cluster == -1:
            return results # Could not determine query cluster

        reranked_results = []
        cluster_bonus = 1.0 # Bonus for being in the same cluster
        for result in results:
            doc_id = result['doc_id']
            original_score = result['score']
            doc_cluster = models['doc_id_to_cluster'].get(doc_id, -1)
            
            new_score = original_score
            if doc_cluster == query_cluster:
                new_score += cluster_bonus
            
            reranked_results.append({'doc_id': doc_id, 'score': new_score, 'cluster_id': int(doc_cluster)})

        reranked_results.sort(key=lambda x: x['score'], reverse=True)
        return reranked_results
    
    # --- Method for query suggestions ---
    def get_suggestions(self, dataset_name: str, prefix: str, limit: int = 10):
        """
        Finds terms in the inverted index that start with the given prefix,
        prioritizing more frequent terms.
        """
        # Load the models to get access to the inverted index
        models = self._load_models(dataset_name)
        prefix = prefix.lower()
        
        # Find all terms that start with the prefix
        matching_terms = [term for term in models['inverted_index'].keys() if term.startswith(prefix)]
        
        # Sort the matching terms by their document frequency (length of the posting list) in descending order
        sorted_suggestions = sorted(matching_terms, key=lambda term: len(models['inverted_index'][term]), reverse=True)
        
        # Return the top 'limit' suggestions
        return sorted_suggestions[:limit]

    # --- Method for spelling correction and alternative query suggestions ---
    def get_alternative_suggestions(self, dataset_name: str, query: str, limit: int = 5):
        # 1. Spelling Correction
        corrected_query = ' '.join(self.spell_checker.correction(word) for word in query.split())
        suggestions = {"corrected_query": corrected_query if corrected_query != query else None}

        # 2. Query Log Suggestions
        try:
            cnx = self._get_db_connection()
            cursor = cnx.cursor(dictionary=True)
            # Find successful queries that are similar to the user's query
            sql = ( "SELECT query_text, COUNT(*) as frequency FROM query_logs "
                    "WHERE dataset_name = %s AND successful = 1 AND query_text LIKE %s AND query_text != %s "
                    "GROUP BY query_text ORDER BY frequency DESC LIMIT %s")
            # Use a broad LIKE match to find related queries
            like_query = f"%{query}%"
            cursor.execute(sql, (dataset_name, like_query, query, limit))
            log_suggestions = [row['query_text'] for row in cursor.fetchall()]
            cursor.close()
            cnx.close()
            suggestions["log_suggestions"] = log_suggestions
        except mysql.connector.Error as err:
            print(f"Failed to get log suggestions: {err}", flush=True)
            suggestions["log_suggestions"] = []
        
        return suggestions

# --- Create a single instance of the service to be used by the API endpoints ---
service = SearchService()

# --- Define the API endpoints ---

# The main search endpoint
@app.post("/search/", response_model=SearchResponse)
async def search_endpoint(request: SearchRequest):
    # Call the main search method of our service instance
    results = service.search(request)
    # Return the results wrapped in the SearchResponse model
    return SearchResponse(results=results)

# The query suggestion endpoint
@app.get("/suggest/", response_model=List[str])
async def suggest_endpoint(dataset_name: str, query: str, limit: int = 10):
    """
    Provides real-time query suggestions based on the last word being typed.
    
    - Handles multi-word queries.
    - Suggestions are ranked by term frequency in the corpus.
    - Returns full query suggestions.
    """
    # If query is empty, there's nothing to suggest.
    # If it ends with a space, the user has completed a word, so we don't suggest.
    if not query or query.endswith(' '):
        return []

    # Split the query to find the last word (the prefix) and the preceding text (the base).
    query_parts = query.rsplit(' ', 1)
    if len(query_parts) > 1:
        base_query, prefix = query_parts[0] + ' ', query_parts[1]
    else:
        base_query, prefix = '', query_parts[0]

    # Don't bother searching if the prefix part is empty (e.g., multiple spaces)
    if not prefix:
        return []

    # Get suggestions for the prefix, which will be sorted by frequency.
    term_suggestions = service.get_suggestions(dataset_name, prefix, limit)
    
    # Combine the base query with each suggestion to form full, ready-to-use query strings.
    full_suggestions = [base_query + term for term in term_suggestions]
    
    return full_suggestions

# The alternative suggestions endpoint
@app.get("/suggest-alternatives/", response_model=dict)
async def suggest_alternatives_endpoint(dataset_name: str, query: str, limit: int = 5):
    """
    Provides spelling correction and alternative query suggestions from logs.
    """
    if not query:
        return {"corrected_query": None, "log_suggestions": []}

    return service.get_alternative_suggestions(dataset_name, query, limit)

