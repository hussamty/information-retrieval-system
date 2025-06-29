# api/representation_api.py

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import mysql.connector
import os
import joblib
import json
from sklearn.feature_extraction.text import TfidfVectorizer
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import pandas as pd
from tqdm import tqdm

from config import DB_CONFIG, MODELS_DIR, EMBEDDING_MODEL_NAME

# --- دوال ثابتة لتجنب مشاكل Pickling ---
def identity_preprocessor(text):
    return text

def space_tokenizer(text):
    return text.split()

class RepresentationRequest(BaseModel):
    dataset_name: str

app = FastAPI(
    title="Robust Representation API",
    description="خدمة لبناء وحفظ نماذج التمثيل، بتصميم موثوق يمنع عدم تطابق البيانات."
)

def build_representations_robust(dataset_name: str):
    """
    Builds all models from a single, unified dataframe to ensure data consistency.
    """
    print(f"Starting ROBUST representation building for dataset: {dataset_name}", flush=True)
    try:
        sanitized_name = dataset_name.replace('/', '_')
        output_dir = os.path.join(MODELS_DIR, sanitized_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # --- الخطوة 1: جلب البيانات الموحد (القلب النابض للحل) ---
        print("Fetching all document data into memory (single source of truth)...", flush=True)
        cnx = mysql.connector.connect(**DB_CONFIG)
        query_all = f"SELECT doc_id, original_text, processed_text FROM documents WHERE dataset = '{dataset_name}'"
        df_master = pd.read_sql(query_all, cnx)
        cnx.close()
        
        # تنظيف نهائي للبيانات لضمان عدم وجود قيم فارغة
        df_master.dropna(subset=['processed_text', 'doc_id'], inplace=True)
        df_master = df_master[df_master['processed_text'] != '']
        df_master.reset_index(drop=True, inplace=True)
        
        print(f"Working with a consistent set of {len(df_master)} documents.", flush=True)

        # استخلاص القوائم الموحدة التي سنستخدمها في كل مكان
        final_doc_ids = df_master['doc_id'].tolist()
        corpus_processed = df_master['processed_text'].tolist()
        corpus_original = df_master['original_text'].tolist()

        # --- الخطوة 2: بناء النماذج التقليدية ---
        print("\n--- Building TF-IDF and BM25 Models ---", flush=True)
        tfidf_vectorizer = TfidfVectorizer(
            max_df=0.9, min_df=5, use_idf=True,
            preprocessor=identity_preprocessor, tokenizer=space_tokenizer
        )
        tfidf_matrix = tfidf_vectorizer.fit_transform(corpus_processed)
        joblib.dump(tfidf_vectorizer, os.path.join(output_dir, 'tfidf_vectorizer.joblib'))
        joblib.dump(tfidf_matrix, os.path.join(output_dir, 'tfidf_matrix.joblib'))
        print("TF-IDF model saved.", flush=True)

        tokenized_corpus = [doc.split() for doc in corpus_processed]
        bm25_model = BM25Okapi(tokenized_corpus)
        joblib.dump(bm25_model, os.path.join(output_dir, 'bm25_model.joblib'))
        print("BM25 model saved.", flush=True)

        # --- الخطوة 3: بناء الفهارس المتقدمة ---
        print("\n--- Building FAISS and Inverted Index ---", flush=True)
        inverted_index = {}
        for i, doc_text in enumerate(corpus_processed):
            for term in doc_text.split():
                if term not in inverted_index: inverted_index[term] = []
                inverted_index[term].append(final_doc_ids[i])
        
        with open(os.path.join(output_dir, 'inverted_index.json'), 'w') as f: json.dump(inverted_index, f)
        print("Inverted Index saved.", flush=True)
        
        # بناء FAISS على دفعات للحفاظ على الذاكرة
        bert_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        embedding_dim = bert_model.get_sentence_embedding_dimension()
        faiss_index = faiss.IndexFlatL2(embedding_dim)
        full_embeddings_list = []
        
        print(f"Encoding {len(corpus_original)} documents with BERT (in batches)...", flush=True)
        embeddings = bert_model.encode(
            corpus_original, 
            convert_to_numpy=True, 
            show_progress_bar=True,
            batch_size=128 # يمكن تقليل هذا الرقم أكثر إذا كانت الذاكرة مشكلة
        )
        
        faiss_index.add(embeddings.astype('float32'))
        print("FAISS index built.", flush=True)

        # --- الخطوة 4: حفظ الملفات النهائية ---
        print("\n--- Saving Final Artifacts ---", flush=True)
        np.save(os.path.join(output_dir, 'bert_embeddings.npy'), embeddings.astype('float32'))
        print("Full embeddings matrix saved.", flush=True)
        faiss.write_index(faiss_index, os.path.join(output_dir, 'faiss.index'))
        print("FAISS Index saved.", flush=True)
        joblib.dump(final_doc_ids, os.path.join(output_dir, 'doc_ids.joblib'))
        print("Document IDs saved.", flush=True)
        
        print(f"\nAll representations for '{dataset_name}' built successfully.", flush=True)

    except Exception as e:
        print(f"An error occurred during representation building for '{dataset_name}': {e}", flush=True)

@app.post("/build-representations/")
async def build_representations_endpoint(request: RepresentationRequest, background_tasks: BackgroundTasks):
    dataset_name = request.dataset_name
    print(f"Received request to build representations for: {dataset_name}", flush=True)
    background_tasks.add_task(build_representations_robust, dataset_name)
    
    return {"message": f"Robust representation building for '{dataset_name}' has started."}

