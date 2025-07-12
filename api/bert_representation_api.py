from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import mysql.connector
import os
import joblib
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import pandas as pd
from tqdm import tqdm
from config import DB_CONFIG, MODELS_DIR, EMBEDDING_MODEL_NAME

class RepresentationRequest(BaseModel):
    dataset_name: str

app = FastAPI(
    title="BERT Representation API",
    description="A service for building and saving BERT representations (FAISS index and embeddings)."
)

def build_bert_representation(dataset_name: str):
    print(f"Starting BERT representation building for dataset: {dataset_name}", flush=True)
    try:
        sanitized_name = dataset_name.replace('/', '_')
        output_dir = os.path.join(MODELS_DIR, sanitized_name)
        os.makedirs(output_dir, exist_ok=True)
        
        cnx = mysql.connector.connect(**DB_CONFIG)

        print("\n--- Building FAISS in Batches ---", flush=True)
        DB_BATCH_SIZE = 50000

        bert_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        embedding_dim = bert_model.get_sentence_embedding_dimension()
        faiss_index = faiss.IndexFlatL2(embedding_dim)
        all_doc_ids = []
        full_embeddings_list = []

        cursor = cnx.cursor()
        cursor.execute(f"SELECT COUNT(doc_id) FROM documents WHERE dataset = '{dataset_name}'")
        total_docs = cursor.fetchone()[0]
        
        offset = 0
        with tqdm(total=total_docs, desc="Processing Document Batches") as pbar:
            while offset < total_docs:
                query_batch = f"SELECT doc_id, original_text FROM documents WHERE dataset = '{dataset_name}' LIMIT {offset}, {DB_BATCH_SIZE}"
                df_batch = pd.read_sql(query_batch, cnx)
                
                if df_batch.empty: break

                batch_doc_ids = df_batch['doc_id'].tolist()
                batch_original = df_batch['original_text'].tolist()
                all_doc_ids.extend(batch_doc_ids)

                print(f"\nEncoding {len(batch_original)} documents with BERT...", flush=True)
                batch_embeddings = bert_model.encode(
                    batch_original, convert_to_numpy=True, show_progress_bar=True, batch_size=16
                )
                
                faiss_index.add(batch_embeddings.astype('float32'))
                full_embeddings_list.append(batch_embeddings.astype('float32')) 
                print(f"  - FAISS index now contains {faiss_index.ntotal} vectors.", flush=True)
                
                offset += len(df_batch)
                pbar.update(len(df_batch))
        
        print("\n--- Finalizing and Saving Indexes ---", flush=True)

        if full_embeddings_list:
            full_embeddings_matrix = np.vstack(full_embeddings_list)
            np.save(os.path.join(output_dir, 'bert_embeddings.npy'), full_embeddings_matrix)
            print(f"Full embeddings matrix saved. Shape: {full_embeddings_matrix.shape}", flush=True)

        faiss.write_index(faiss_index, os.path.join(output_dir, 'faiss.index'))
        print("FAISS Index saved.", flush=True)
        joblib.dump(all_doc_ids, os.path.join(output_dir, 'doc_ids.joblib'))
        print("Document IDs saved.", flush=True)

        cnx.close()
        print(f"\nBERT representation for '{dataset_name}' built successfully.", flush=True)

    except Exception as e:
        print(f"An error occurred during BERT representation building for '{dataset_name}': {e}", flush=True)

@app.post("/build-bert-representation/")
async def build_bert_representation_endpoint(request: RepresentationRequest, background_tasks: BackgroundTasks):
    dataset_name = request.dataset_name
    print(f"Received request to build BERT representation for: {dataset_name}", flush=True)
    background_tasks.add_task(build_bert_representation, dataset_name)
    
    return {"message": f"BERT representation building for '{dataset_name}' has started."}
