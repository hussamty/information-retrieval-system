from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import mysql.connector
import os
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
import pandas as pd
from config import DB_CONFIG, MODELS_DIR

def identity_preprocessor(text):
    return text

def space_tokenizer(text):
    return text.split()

class RepresentationRequest(BaseModel):
    dataset_name: str

app = FastAPI(
    title="TF-IDF Representation API",
    description="A service for building and saving TF-IDF representations."
)

def build_tfidf_representation(dataset_name: str):
    print(f"Starting TF-IDF representation building for dataset: {dataset_name}", flush=True)
    try:
        sanitized_name = dataset_name.replace('/', '_')
        output_dir = os.path.join(MODELS_DIR, sanitized_name)
        os.makedirs(output_dir, exist_ok=True)
        
        cnx = mysql.connector.connect(**DB_CONFIG)

        print("\n--- Building TF-IDF In-Memory ---", flush=True)
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
        
        del df_processed, corpus_processed
        print("Memory from TF-IDF build has been freed.", flush=True)

        cnx.close()
        print(f"\nTF-IDF representation for '{dataset_name}' built successfully.", flush=True)

    except Exception as e:
        print(f"An error occurred during TF-IDF representation building for '{dataset_name}': {e}", flush=True)

@app.post("/build-tfidf-representation/")
async def build_tfidf_representation_endpoint(request: RepresentationRequest, background_tasks: BackgroundTasks):
    dataset_name = request.dataset_name
    print(f"Received request to build TF-IDF representation for: {dataset_name}", flush=True)
    background_tasks.add_task(build_tfidf_representation, dataset_name)
    
    return {"message": f"TF-IDF representation building for '{dataset_name}' has started."}
