# api/search_api.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
import os
import joblib
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import faiss
import mysql.connector

from core.text_preprocessor import TextPreprocessor
from config import MODELS_DIR, EMBEDDING_MODEL_NAME, DB_CONFIG

class SearchRequest(BaseModel):
    dataset_name: str
    query: str
    model_type: str = Field("hybrid", description="'tfidf', 'bm25', 'bert', or 'hybrid'")
    top_k: int = 10
    k1: float = 1.5
    b: float = 0.75
    enable_ner_reranking: bool = False
    hybrid_bm25_weight: float = 0.8 # <<<< معامل جديد لوزن BM25 في النموذج الهجين

class SearchResult(BaseModel):
    doc_id: str
    score: float

class SearchResponse(BaseModel):
    results: List[SearchResult]

app = FastAPI(
    title="Advanced Search API with Re-ranking and Weighted Hybrid",
    description="الخدمة المركزية للبحث. تطبق المجموع الموزون للنموذج الهجين."
)

class SearchService:
    # ... (The __init__, _get_db_connection, _fetch_original_texts, and _load_models functions remain the same)
    def __init__(self):
        self.preprocessor = TextPreprocessor()
        self.loaded_models = {}
        self.doc_text_cache = {}

    def _get_db_connection(self):
        return mysql.connector.connect(**DB_CONFIG)

    def _fetch_original_texts(self, doc_ids, dataset_name):
        texts, ids_to_fetch = {}, []
        for doc_id in doc_ids:
            if doc_id in self.doc_text_cache: texts[doc_id] = self.doc_text_cache[doc_id]
            else: ids_to_fetch.append(doc_id)
        if ids_to_fetch:
            try:
                cnx = self._get_db_connection()
                cursor = cnx.cursor(dictionary=True)
                placeholders = ', '.join(['%s'] * len(ids_to_fetch))
                sql = f"SELECT doc_id, original_text FROM documents WHERE doc_id IN ({placeholders}) AND dataset = %s"
                params = ids_to_fetch + [dataset_name]
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    self.doc_text_cache[row['doc_id']] = row['original_text']
                    texts[row['doc_id']] = row['original_text']
                cursor.close(); cnx.close()
            except mysql.connector.Error: pass
        return texts

    def _load_models(self, dataset_name):
        if dataset_name in self.loaded_models: return self.loaded_models[dataset_name]
        sanitized_name = dataset_name.replace('/', '_')
        model_dir = os.path.join(MODELS_DIR, sanitized_name)
        if not os.path.exists(model_dir): raise HTTPException(status_code=404, detail=f"Models for dataset '{dataset_name}' not found.")
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
        models['doc_id_to_idx'] = {doc_id: i for i, doc_id in enumerate(models['doc_ids'])}
        self.loaded_models[dataset_name] = models
        return models

    # ... (_search_tfidf, _search_bm25, _search_bert functions remain the same)
    def _search_tfidf(self, query, models, k):
        query_terms, candidate_docs_set = query.split(), set()
        for term in query_terms:
            if term in models['inverted_index']: candidate_docs_set.update(models['inverted_index'][term])
        if not candidate_docs_set: return []
        candidate_doc_ids = list(candidate_docs_set)
        candidate_indices = [models['doc_id_to_idx'][doc_id] for doc_id in candidate_doc_ids if doc_id in models['doc_id_to_idx']]
        if not candidate_indices: return []
        query_vec = models['tfidf_vectorizer'].transform([query])
        candidate_matrix = models['tfidf_matrix'][candidate_indices]
        scores = cosine_similarity(query_vec, candidate_matrix).flatten()
        scored_candidates = zip([candidate_doc_ids[i] for i in range(len(candidate_indices))], scores)
        sorted_results = sorted(scored_candidates, key=lambda item: item[1], reverse=True)
        return [{'doc_id': doc_id, 'score': float(score)} for doc_id, score in sorted_results[:k] if score > 0]
    
    def _search_bm25(self, query, models, k, k1, b):
        models['bm25_model'].k1 = k1; models['bm25_model'].b = b
        scores = models['bm25_model'].get_scores(query.split())
        indices = np.argsort(scores)[-k:][::-1]
        return [{'doc_id': models['doc_ids'][i], 'score': float(scores[i])} for i in indices if scores[i] > 0]

    def _search_bert(self, query, models, k):
        query_embedding = models['bert_model'].encode([query]).astype('float32')
        distances, indices = models['faiss_index'].search(query_embedding, k)
        scores = 1 / (1 + distances[0])
        return [{'doc_id': models['doc_ids'][i], 'score': float(scores[idx])} for idx, i in enumerate(indices[0])]


    # --- التعديل الأهم: تطبيق المجموع الموزون ---
    def _search_hybrid_weighted_sum(self, processed_query, original_query, models, k, k1, b, bm25_weight):
        print(f"Executing Weighted Sum Hybrid Search with BM25 weight: {bm25_weight}")
        bm25_res = self._search_bm25(processed_query, models, k, k1, b)
        bert_res = self._search_bert(original_query, models, k)

        # تحويل النتائج إلى قواميس لسهولة الوصول
        bm25_scores = {res['doc_id']: res['score'] for res in bm25_res}
        bert_scores = {res['doc_id']: res['score'] for res in bert_res}
        
        # دالة لتسوية الدرجات (Min-Max Normalization)
        def normalize(scores_dict):
            if not scores_dict: return {}
            scores = list(scores_dict.values())
            min_score, max_score = min(scores), max(scores)
            if max_score == min_score: return {doc_id: 1.0 for doc_id in scores_dict}
            return {doc_id: (score - min_score) / (max_score - min_score) for doc_id, score in scores_dict.items()}

        norm_bm25 = normalize(bm25_scores)
        norm_bert = normalize(bert_scores)

        # دمج الدرجات باستخدام المجموع الموزون
        final_scores = {}
        all_ids = set(norm_bm25.keys()).union(set(norm_bert.keys()))
        
        bert_weight = 1 - bm25_weight

        for doc_id in all_ids:
            score1 = norm_bm25.get(doc_id, 0)
            score2 = norm_bert.get(doc_id, 0)
            final_scores[doc_id] = (bm25_weight * score1) + (bert_weight * score2)

        sorted_docs = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)
        return [{'doc_id': doc_id, 'score': score} for doc_id, score in sorted_docs[:k]]


    def search(self, req: SearchRequest):
        models = self._load_models(req.dataset_name)
        processed_query = self.preprocessor.preprocess(req.query)
        
        initial_retrieval_size = 50 if req.enable_ner_reranking else req.top_k
        
        # --- المرحلة الأولى: الجلب الأولي ---
        if req.model_type == 'hybrid':
            initial_results = self._search_hybrid_weighted_sum(
                processed_query, req.query, models, initial_retrieval_size,
                req.k1, req.b, req.hybrid_bm25_weight
            )
        else:
            base_model_map = {
                'tfidf': lambda: self._search_tfidf(processed_query, models, initial_retrieval_size),
                'bm25': lambda: self._search_bm25(processed_query, models, initial_retrieval_size, req.k1, req.b),
                'bert': lambda: self._search_bert(req.query, models, initial_retrieval_size)
            }
            if req.model_type not in base_model_map: raise HTTPException(status_code=400, detail="Invalid model_type")
            initial_results = base_model_map[req.model_type]()

        # --- المرحلة الثانية: إعادة الترتيب (إذا تم تفعيلها) ---
        if not initial_results or not req.enable_ner_reranking:
            return initial_results[:req.top_k]

        query_entities = self.preprocessor.extract_entities(req.query)
        if not query_entities: return initial_results[:req.top_k]
        
        candidate_ids = [res['doc_id'] for res in initial_results]
        candidate_texts = self._fetch_original_texts(candidate_ids, req.dataset_name)
        
        reranked_results = []
        ner_bonus = 0.5 
        
        for result in initial_results:
            doc_id, original_score = result['doc_id'], result['score']
            doc_text = candidate_texts.get(doc_id, "")
            doc_entities = self.preprocessor.extract_entities(doc_text)
            matching_entities_count = len(query_entities.intersection(doc_entities))
            final_score = original_score + (matching_entities_count * ner_bonus)
            reranked_results.append({'doc_id': doc_id, 'score': final_score})
            
        reranked_results.sort(key=lambda x: x['score'], reverse=True)
        return reranked_results[:req.top_k]

service = SearchService()

@app.post("/search/", response_model=SearchResponse)
async def search_endpoint(request: SearchRequest):
    results = service.search(request)
    return SearchResponse(results=results)

