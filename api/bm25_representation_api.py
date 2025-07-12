from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import mysql.connector
import os
import joblib
from rank_bm25 import BM25Okapi
import pandas as pd
from config import DB_CONFIG, MODELS_DIR

class RepresentationRequest(BaseModel):
    dataset_name: str

app = FastAPI(
    title="BM25 Representation API",
    description="A service for building and saving BM25 representations."
)

def build_bm25_representation(dataset_name: str):
    print(f"Starting BM25 representation building for dataset: {dataset_name}", flush=True)
    try:
        sanitized_name = dataset_name.replace('/', '_')
        output_dir = os.path.join(MODELS_DIR, sanitized_name)
        os.makedirs(output_dir, exist_ok=True)
        
        cnx = mysql.connector.connect(**DB_CONFIG)

        print("\n--- Building BM25 In-Memory ---", flush=True)
        query_processed = f"SELECT processed_text FROM documents WHERE dataset = '{dataset_name}' AND processed_text IS NOT NULL AND processed_text != ''"
        df_processed = pd.read_sql(query_processed, cnx)
        corpus_processed = df_processed['processed_text'].tolist()
        
        print(f"Building BM25 model on {len(corpus_processed)} documents...", flush=True)
        tokenized_corpus_generator = (doc.split() for doc in corpus_processed)
        bm25_model = BM25Okapi(tokenized_corpus_generator)
        joblib.dump(bm25_model, os.path.join(output_dir, 'bm25_model.joblib'))
        print("BM25 model saved.", flush=True)
        
        del df_processed, corpus_processed, tokenized_corpus_generator
        print("Memory from BM25 build has been freed.", flush=True)

        cnx.close()
        print(f"\nBM25 representation for '{dataset_name}' built successfully.", flush=True)

    except Exception as e:
        print(f"An error occurred during BM25 representation building for '{dataset_name}': {e}", flush=True)

@app.post("/build-bm25-representation/")
async def build_bm25_representation_endpoint(request: RepresentationRequest, background_tasks: BackgroundTasks):
    dataset_name = request.dataset_name
    print(f"Received request to build BM25 representation for: {dataset_name}", flush=True)
    background_tasks.add_task(build_bm25_representation, dataset_name)
    
    return {"message": f"BM25 representation building for '{dataset_name}' has started."}
