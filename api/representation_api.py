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
    title="Memory-Safe Representation API",
    description="خدمة لبناء وحفظ نماذج التمثيل، مصممة للعمل بكفاءة مع البيانات الضخمة."
)

def build_representations_robust(dataset_name: str):
    print(f"Starting ROBUST representation building for dataset: {dataset_name}", flush=True)
    try:
        sanitized_name = dataset_name.replace('/', '_')
        output_dir = os.path.join(MODELS_DIR, sanitized_name)
        os.makedirs(output_dir, exist_ok=True)
        
        cnx = mysql.connector.connect(**DB_CONFIG)

        # --- المرحلة الأولى: بناء TF-IDF و BM25 دفعة واحدة ---
        print("\n--- STAGE 1: Building TF-IDF and BM25 In-Memory ---", flush=True)
        query_processed = f"SELECT processed_text FROM documents WHERE dataset = '{dataset_name}' AND processed_text IS NOT NULL AND processed_text != ''"
        df_processed = pd.read_sql(query_processed, cnx)
        corpus_processed = df_processed['processed_text'].tolist()
        
        print(f"Building TF-IDF model on {len(corpus_processed)} documents...", flush=True)
        tfidf_vectorizer = TfidfVectorizer(
            max_df=0.9, min_df=5, use_idf=True,
            preprocessor=identity_preprocessor, tokenizer=space_tokenizer
        )
        tfidf_matrix = tfidf_vectorizer.fit_transform(corpus_processed)
        joblib.dump(tfidf_vectorizer, os.path.join(output_dir, 'tfidf_vectorizer.joblib'))
        joblib.dump(tfidf_matrix, os.path.join(output_dir, 'tfidf_matrix.joblib'))
        print("TF-IDF model saved.", flush=True)

        print(f"Building BM25 model on {len(corpus_processed)} documents...", flush=True)
        tokenized_corpus_generator = (doc.split() for doc in corpus_processed)
        bm25_model = BM25Okapi(tokenized_corpus_generator)
        joblib.dump(bm25_model, os.path.join(output_dir, 'bm25_model.joblib'))
        print("BM25 model saved.", flush=True)
        
        del df_processed, corpus_processed, tokenized_corpus_generator
        print("Memory from Stage 1 has been freed.", flush=True)

        # --- المرحلة الثانية: بناء الفهارس الأخرى على دفعات ---
        print("\n--- STAGE 2: Building FAISS and Inverted Index in Batches ---", flush=True)
        DB_BATCH_SIZE = 50000

        inverted_index = {}
        bert_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        embedding_dim = bert_model.get_sentence_embedding_dimension()
        faiss_index = faiss.IndexFlatL2(embedding_dim)
        all_doc_ids = []
        full_embeddings_list = [] # <<<< قائمة لتجميع كل متجهات الدفعات

        cursor = cnx.cursor()
        cursor.execute(f"SELECT COUNT(doc_id) FROM documents WHERE dataset = '{dataset_name}'")
        total_docs = cursor.fetchone()[0]
        
        offset = 0
        with tqdm(total=total_docs, desc="Processing Document Batches") as pbar:
            while offset < total_docs:
                query_batch = f"SELECT doc_id, original_text, processed_text FROM documents WHERE dataset = '{dataset_name}' LIMIT {offset}, {DB_BATCH_SIZE}"
                df_batch = pd.read_sql(query_batch, cnx)
                
                if df_batch.empty: break

                batch_doc_ids = df_batch['doc_id'].tolist()
                batch_original = df_batch['original_text'].tolist()
                batch_processed = df_batch['processed_text'].tolist()
                all_doc_ids.extend(batch_doc_ids)

                for i, doc_text in enumerate(batch_processed):
                    if not isinstance(doc_text, str): continue
                    for term in doc_text.split():
                        if term not in inverted_index: inverted_index[term] = []
                        inverted_index[term].append(batch_doc_ids[i])

                print(f"\nEncoding {len(batch_original)} documents with BERT...", flush=True)
                batch_embeddings = bert_model.encode(
                    batch_original, convert_to_numpy=True, show_progress_bar=True, batch_size=16
                )
                
                faiss_index.add(batch_embeddings.astype('float32'))
                full_embeddings_list.append(batch_embeddings.astype('float32')) # <<<< تجميع المتجهات هنا
                print(f"  - FAISS index now contains {faiss_index.ntotal} vectors.", flush=True)
                
                offset += len(df_batch)
                pbar.update(len(df_batch))
        
        # --- المرحلة الثالثة: حفظ الفهارس والمصفوفة الكاملة ---
        print("\n--- Finalizing and Saving Indexes ---", flush=True)

        # --- هذا هو الكود الذي تمت إعادته ---
        if full_embeddings_list:
            full_embeddings_matrix = np.vstack(full_embeddings_list)
            np.save(os.path.join(output_dir, 'bert_embeddings.npy'), full_embeddings_matrix)
            print(f"Full embeddings matrix saved. Shape: {full_embeddings_matrix.shape}", flush=True)
        # ------------------------------------

        with open(os.path.join(output_dir, 'inverted_index.json'), 'w') as f: json.dump(inverted_index, f)
        print("Inverted Index saved.", flush=True)
        faiss.write_index(faiss_index, os.path.join(output_dir, 'faiss.index'))
        print("FAISS Index saved.", flush=True)
        joblib.dump(all_doc_ids, os.path.join(output_dir, 'doc_ids.joblib'))
        print("Document IDs saved.", flush=True)

        cnx.close()
        print(f"\nAll representations for '{dataset_name}' built successfully.", flush=True)

    except Exception as e:
        print(f"An error occurred during representation building for '{dataset_name}': {e}", flush=True)

@app.post("/build-representations/")
async def build_representations_endpoint(request: RepresentationRequest, background_tasks: BackgroundTasks):
    dataset_name = request.dataset_name
    print(f"Received request to build representations for: {dataset_name}", flush=True)
    background_tasks.add_task(build_representations_robust, dataset_name)
    
    return {"message": f"Memory-safe representation building for '{dataset_name}' has started."}

