from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import mysql.connector
import os
import json
import pandas as pd
from tqdm import tqdm
from config import DB_CONFIG, MODELS_DIR

class RepresentationRequest(BaseModel):
    dataset_name: str

app = FastAPI(
    title="Inverted Index Representation API",
    description="A service for building and saving Inverted Index representations."
)

def build_inverted_index_representation(dataset_name: str):
    print(f"Starting Inverted Index representation building for dataset: {dataset_name}", flush=True)
    try:
        sanitized_name = dataset_name.replace('/', '_')
        output_dir = os.path.join(MODELS_DIR, sanitized_name)
        os.makedirs(output_dir, exist_ok=True)
        
        cnx = mysql.connector.connect(**DB_CONFIG)

        print("\n--- Building Inverted Index in Batches ---", flush=True)
        DB_BATCH_SIZE = 50000

        inverted_index = {}

        cursor = cnx.cursor()
        cursor.execute(f"SELECT COUNT(doc_id) FROM documents WHERE dataset = '{dataset_name}'")
        total_docs = cursor.fetchone()[0]
        
        offset = 0
        with tqdm(total=total_docs, desc="Processing Document Batches") as pbar:
            while offset < total_docs:
                query_batch = f"SELECT doc_id, processed_text FROM documents WHERE dataset = '{dataset_name}' LIMIT {offset}, {DB_BATCH_SIZE}"
                df_batch = pd.read_sql(query_batch, cnx)
                
                if df_batch.empty: break

                batch_doc_ids = df_batch['doc_id'].tolist()
                batch_processed = df_batch['processed_text'].tolist()

                for i, doc_text in enumerate(batch_processed):
                    if not isinstance(doc_text, str): continue
                    for term in doc_text.split():
                        if term not in inverted_index: inverted_index[term] = []
                        inverted_index[term].append(batch_doc_ids[i])
                
                offset += len(df_batch)
                pbar.update(len(df_batch))
        
        print("\n--- Finalizing and Saving Index ---", flush=True)

        with open(os.path.join(output_dir, 'inverted_index.json'), 'w') as f: json.dump(inverted_index, f)
        print("Inverted Index saved.", flush=True)

        cnx.close()
        print(f"\nInverted Index representation for '{dataset_name}' built successfully.", flush=True)

    except Exception as e:
        print(f"An error occurred during Inverted Index representation building for '{dataset_name}': {e}", flush=True)

@app.post("/build-inverted-index-representation/")
async def build_inverted_index_representation_endpoint(request: RepresentationRequest, background_tasks: BackgroundTasks):
    dataset_name = request.dataset_name
    print(f"Received request to build Inverted Index representation for: {dataset_name}", flush=True)
    background_tasks.add_task(build_inverted_index_representation, dataset_name)
    
    return {"message": f"Inverted Index representation building for '{dataset_name}' has started."}
