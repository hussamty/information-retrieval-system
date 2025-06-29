# api/data_loader_api.py

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import ir_datasets
import mysql.connector
from tqdm import tqdm

from core.text_preprocessor import TextPreprocessor
from config import DB_CONFIG

class DatasetRequest(BaseModel):
    dataset_name: str

app = FastAPI(
    title="Data Loader and Preprocessing API",
    description="خدمة لتحميل مجموعات البيانات من ir_datasets، معالجتها، وتخزينها في قاعدة البيانات."
)

def process_and_store(dataset_name: str):
    """
    The actual function that runs in the background.
    This version uses batch commits and forced flushing of print statements
    to provide accurate real-time logging.
    """
    print(f"Starting background task for dataset: {dataset_name}", flush=True)
    BATCH_SIZE = 10000 
    
    try:
        dataset = ir_datasets.load(dataset_name)
        preprocessor = TextPreprocessor()
        cnx = mysql.connector.connect(**DB_CONFIG)
        cursor = cnx.cursor()

        sql_insert = (
            "INSERT INTO documents (doc_id, dataset, original_text, processed_text) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE original_text=%s, processed_text=%s"
        )

        print(f"Processing and storing documents for '{dataset_name}' in batches of {BATCH_SIZE}...", flush=True)
        
        doc_count = 0
        for doc in tqdm(dataset.docs_iter(), total=dataset.docs_count()):
            if not hasattr(doc, 'text') or not doc.text:
                continue
            
            original_text = doc.text
            processed_text = preprocessor.preprocess(original_text)
            
            cursor.execute(sql_insert, (
                doc.doc_id, dataset_name, original_text, processed_text,
                original_text, processed_text
            ))
            
            doc_count += 1
            
            # Commit the transaction after each batch
            if doc_count % BATCH_SIZE == 0:
                print(f"\nReached batch size {BATCH_SIZE}. Committing to database...", flush=True)
                cnx.commit()
                print(f"  - Commit successful for batch. Total documents processed: {doc_count}", flush=True)

        # Commit the final remaining batch
        print("\nLoop finished. Committing final batch...", flush=True)
        cnx.commit()
        print(f"  - Final commit successful. Total documents processed: {doc_count}", flush=True)

        cursor.close()
        cnx.close()
        print(f"Successfully finished processing and storing for '{dataset_name}'.", flush=True)

    except Exception as e:
        print(f"\nAn error occurred during processing for '{dataset_name}': {e}", flush=True)


@app.post("/load-dataset/")
async def load_dataset_endpoint(request: DatasetRequest, background_tasks: BackgroundTasks):
    dataset_name = request.dataset_name
    print(f"Received request to load dataset: {dataset_name}", flush=True)
    background_tasks.add_task(process_and_store, dataset_name)
    
    return {
        "message": f"Data loading and processing for '{dataset_name}' has started in the background."
    }

