# Import necessary libraries
from fastapi import FastAPI, BackgroundTasks, HTTPException # For creating the API and running background tasks
from pydantic import BaseModel # For defining the structure of API requests
import mysql.connector # To connect to the MySQL database
import os # For interacting with the operating system, like creating directories
import joblib # For saving and loading Python objects (like ML models) efficiently
import json # For working with JSON data (saving the inverted index)
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer # To create a TF-IDF representation
from sklearn.cluster import KMeans # To perform K-Means clustering on the data
from sklearn.decomposition import LatentDirichletAllocation # For topic modeling
from rank_bm25 import BM25Okapi # To create a BM25 representation for ranking
from sentence_transformers import SentenceTransformer # To create sentence embeddings using models like BERT
import faiss # A library from Facebook AI for efficient similarity search
import numpy as np # A fundamental package for numerical computation
import pandas as pd # For data manipulation and analysis, especially for reading data from SQL
from tqdm import tqdm # To display progress bars
from typing import Optional

# Import custom configuration and constants
from config import DB_CONFIG, MODELS_DIR, EMBEDDING_MODEL_NAME

# --- Helper functions to avoid issues with saving/loading models (pickling) ---
# A dummy function that just returns the text as is. Used because TfidfVectorizer expects a preprocessor.
def identity_preprocessor(text):
    return text

# A simple tokenizer that splits text by spaces. Used for TfidfVectorizer.
def space_tokenizer(text):
    return text.split()

# Define the structure for a request to build representations
class RepresentationRequest(BaseModel):
    dataset_name: str

# Define the structure for a request to build clusters
class ClusterRequest(BaseModel):
    dataset_name: str
    num_clusters: int = 20
    use_bert: Optional[bool] = False  

# Create a new FastAPI application instance
app = FastAPI(
    title="Memory-Safe Representation API",
    description="A service for building, saving representations, designed to handle large datasets."
)

# The main function to build all the different data representations
def build_representations_robust(dataset_name: str):
    # Print a starting message, flushing to ensure it appears immediately
    print(f"Starting ROBUST representation building for dataset: {dataset_name}", flush=True)
    try:
        # Sanitize the dataset name to use it as a valid directory name (e.g., 'ms/marco' -> 'ms_marco')
        sanitized_name = dataset_name.replace('/', '_')
        # Define the directory where models for this dataset will be saved
        output_dir = os.path.join(MODELS_DIR, sanitized_name)
        # Create the directory if it doesn't already exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Connect to the MySQL database
        cnx = mysql.connector.connect(**DB_CONFIG)

        # --- STAGE 1: Build TF-IDF and BM25. These are done in memory as they need the full corpus at once. ---
        print("\n--- STAGE 1: Building TF-IDF and BM25 In-Memory ---", flush=True)
        # SQL query to get all processed (cleaned) text from the database for the given dataset
        query_processed = f"SELECT processed_text FROM documents WHERE dataset = '{dataset_name}' AND processed_text IS NOT NULL AND processed_text != ''"
        # Use pandas to execute the query and load the results into a DataFrame
        df_processed = pd.read_sql(query_processed, cnx)
        # Convert the 'processed_text' column of the DataFrame into a list of strings
        corpus_processed = df_processed['processed_text'].tolist()
        
        # Build the TF-IDF model
        print(f"Building TF-IDF model on {len(corpus_processed)} documents...", flush=True)
        # Initialize the TfidfVectorizer with specific parameters
        tfidf_vectorizer = TfidfVectorizer(
            max_df=0.9, min_df=5, use_idf=True, # Ignore terms that are too frequent or too rare
            preprocessor=identity_preprocessor, tokenizer=space_tokenizer # Use our custom dummy functions
        )
        # Fit the vectorizer to the data and transform the corpus into a TF-IDF matrix
        tfidf_matrix = tfidf_vectorizer.fit_transform(corpus_processed)
        # Save the vectorizer and the matrix to disk using joblib
        joblib.dump(tfidf_vectorizer, os.path.join(output_dir, 'tfidf_vectorizer.joblib'))
        joblib.dump(tfidf_matrix, os.path.join(output_dir, 'tfidf_matrix.joblib'))
        print("TF-IDF model saved.", flush=True)

        # Build the BM25 model
        print(f"Building BM25 model on {len(corpus_processed)} documents...", flush=True)
        # BM25 requires a list of lists of tokens, so we create a generator to split each document
        tokenized_corpus_generator = (doc.split() for doc in corpus_processed)
        # Initialize and build the BM25 model
        bm25_model = BM25Okapi(tokenized_corpus_generator)
        # Save the BM25 model to disk
        joblib.dump(bm25_model, os.path.join(output_dir, 'bm25_model.joblib'))
        print("BM25 model saved.", flush=True)
        
        # Free up memory by deleting the large objects we no longer need
        del df_processed, corpus_processed, tokenized_corpus_generator
        print("Memory from Stage 1 has been freed.", flush=True)

        # --- STAGE 2: Build FAISS and Inverted Index in smaller batches to conserve memory ---
        print("\n--- STAGE 2: Building FAISS and Inverted Index in Batches ---", flush=True)
        # Define the number of documents to process from the database in each batch
        DB_BATCH_SIZE = 50000

        # Initialize an empty dictionary for the inverted index
        inverted_index = {}
        # Load the pre-trained Sentence Transformer model for creating embeddings
        bert_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        # Get the dimension of the embeddings produced by the model (e.g., 768)
        embedding_dim = bert_model.get_sentence_embedding_dimension()
        # Initialize a flat FAISS index. 'IndexFlatL2' uses L2 distance for searching.
        faiss_index = faiss.IndexFlatL2(embedding_dim)
        # Initialize lists to store all document IDs and their corresponding embeddings
        all_doc_ids = []
        full_embeddings_list = [] # List to gather embeddings from all batches

        # Get the total number of documents to process for the progress bar
        cursor = cnx.cursor()
        cursor.execute(f"SELECT COUNT(doc_id) FROM documents WHERE dataset = '{dataset_name}'")
        total_docs = cursor.fetchone()[0]
        
        # Process the documents in batches
        offset = 0
        with tqdm(total=total_docs, desc="Processing Document Batches") as pbar:
            while offset < total_docs:
                # SQL query to fetch a batch of documents using LIMIT and OFFSET
                query_batch = f"SELECT doc_id, original_text, processed_text FROM documents WHERE dataset = '{dataset_name}' LIMIT {offset}, {DB_BATCH_SIZE}"
                df_batch = pd.read_sql(query_batch, cnx)
                
                # If the batch is empty, we've processed all documents, so break the loop
                if df_batch.empty: break

                # Get the data from the current batch
                batch_doc_ids = df_batch['doc_id'].tolist()
                batch_original = df_batch['original_text'].tolist()
                batch_processed = df_batch['processed_text'].tolist()
                # Add the document IDs from this batch to our master list
                all_doc_ids.extend(batch_doc_ids)

                # Build the inverted index for the current batch
                for i, doc_text in enumerate(batch_processed):
                    if not isinstance(doc_text, str): continue # Skip if text is not a string
                    # For each term in the processed text
                    for term in doc_text.split():
                        # If the term is new, create a new list for it in the index
                        if term not in inverted_index: inverted_index[term] = []
                        # Append the current document's ID to the term's list
                        inverted_index[term].append(batch_doc_ids[i])

                # Generate BERT embeddings for the original text in the batch
                print(f"\nEncoding {len(batch_original)} documents with BERT...", flush=True)
                batch_embeddings = bert_model.encode(
                    batch_original, convert_to_numpy=True, show_progress_bar=True, batch_size=16
                )
                
                # Add the generated embeddings to the FAISS index
                faiss_index.add(batch_embeddings.astype('float32'))
                # Append the batch embeddings to our list for later saving
                full_embeddings_list.append(batch_embeddings.astype('float32')) 
                print(f"  - FAISS index now contains {faiss_index.ntotal} vectors.", flush=True)
                
                # Move to the next batch
                offset += len(df_batch)
                # Update the progress bar
                pbar.update(len(df_batch))
        
        # --- STAGE 3: Save the remaining indexes and the full embeddings matrix ---
        print("\n--- Finalizing and Saving Indexes ---", flush=True)

        # Check if we have any embeddings to save
        if full_embeddings_list:
            # Stack all the batch embeddings vertically to create one large NumPy matrix
            full_embeddings_matrix = np.vstack(full_embeddings_list)
            # Save the full matrix to a .npy file
            np.save(os.path.join(output_dir, 'bert_embeddings.npy'), full_embeddings_matrix)
            print(f"Full embeddings matrix saved. Shape: {full_embeddings_matrix.shape}", flush=True)

        # Save the inverted index to a JSON file
        with open(os.path.join(output_dir, 'inverted_index.json'), 'w') as f: json.dump(inverted_index, f)
        print("Inverted Index saved.", flush=True)
        # Save the FAISS index to a file
        faiss.write_index(faiss_index, os.path.join(output_dir, 'faiss.index'))
        print("FAISS Index saved.", flush=True)
        # Save the master list of document IDs
        joblib.dump(all_doc_ids, os.path.join(output_dir, 'doc_ids.joblib'))
        print("Document IDs saved.", flush=True)

        # Close the database connection
        cnx.close()
        print(f"\nAll representations for '{dataset_name}' built successfully.", flush=True)

    except Exception as e:
        # Catch and print any errors that occurred during the process
        print(f"An error occurred during representation building for '{dataset_name}': {e}", flush=True)

# Define the API endpoint for building representations
@app.post("/build-representations/")
async def build_representations_endpoint(request: RepresentationRequest, background_tasks: BackgroundTasks):
    dataset_name = request.dataset_name
    print(f"Received request to build representations for: {dataset_name}", flush=True)
    # Add the main building function to run in the background
    background_tasks.add_task(build_representations_robust, dataset_name)
    
    # Return an immediate confirmation message
    return {"message": f"Memory-safe representation building for '{dataset_name}' has started."}


def load_tfidf_matrix(model_dir: str):
    path = os.path.join(model_dir, 'tfidf_matrix.joblib')
    if not os.path.exists(path):
        raise FileNotFoundError(f"TF-IDF matrix not found at {path}. Please build representations first.")
    print(f"[LOAD] TF-IDF matrix loaded from {path}", flush=True)
    return joblib.load(path)

def load_bert_embeddings(model_dir: str):
    path = os.path.join(model_dir, 'bert_embeddings.npy')
    if not os.path.exists(path):
        raise FileNotFoundError(f"BERT embeddings not found at {path}. Please build representations first.")
    print(f"[LOAD] BERT embeddings loaded from {path}", flush=True)
    return np.load(path)


# --- A separate function and endpoint for clustering ---
def perform_clustering(dataset_name: str, num_clusters: int, use_bert: bool = False):
    print(f"[CLUSTERING] Starting clustering for dataset: {dataset_name} with {num_clusters} clusters. Using BERT: {use_bert}", flush=True)
    try:
        if num_clusters <= 0:
            raise ValueError("Number of clusters must be a positive integer.")

        sanitized_name = dataset_name.replace('/', '_')
        model_dir = os.path.join(MODELS_DIR, sanitized_name)

        # Load data matrix
        if use_bert:
            data_matrix = load_bert_embeddings(model_dir)
            # Topic modeling is better suited for sparse data like TF-IDF/Count vectors
            print("[CLUSTERING] Skipping topic modeling for BERT embeddings.", flush=True)
            topic_model_results = None
        else:
            # For TF-IDF, we can also perform topic modeling
            data_matrix = load_tfidf_matrix(model_dir)
            print("[CLUSTERING] Performing Topic Modeling with LDA...", flush=True)
            # We need the raw term counts for LDA, so we create a CountVectorizer
            # We assume the same vocabulary as the TF-IDF model
            tfidf_vectorizer = joblib.load(os.path.join(model_dir, 'tfidf_vectorizer.joblib'))
            
            cnx = mysql.connector.connect(**DB_CONFIG)
            query_processed = f"SELECT processed_text FROM documents WHERE dataset = '{dataset_name}' AND processed_text IS NOT NULL AND processed_text != ''"
            df_processed = pd.read_sql(query_processed, cnx)
            corpus_processed = df_processed['processed_text'].tolist()
            cnx.close()

            count_vectorizer = CountVectorizer(vocabulary=tfidf_vectorizer.vocabulary_,
                                               preprocessor=identity_preprocessor, 
                                               tokenizer=space_tokenizer)
            count_matrix = count_vectorizer.fit_transform(corpus_processed)

            lda = LatentDirichletAllocation(n_components=num_clusters, random_state=42)
            lda.fit(count_matrix)

            # Save the LDA model and the count vectorizer
            joblib.dump(lda, os.path.join(model_dir, 'lda_model.joblib'))
            joblib.dump(count_vectorizer, os.path.join(model_dir, 'count_vectorizer.joblib'))
            print("[CLUSTERING] LDA model saved.", flush=True)

        # Run KMeans
        print(f"[CLUSTERING] Running K-Means...", flush=True)
        kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init='auto')
        clusters = kmeans.fit_predict(data_matrix)

        # Save clusters
        clusters_path = os.path.join(model_dir, 'clusters.joblib')
        joblib.dump(clusters, clusters_path)
        print(f"[CLUSTERING] Clustering complete. Results saved to {clusters_path}", flush=True)

    except Exception as e:
        print(f"[ERROR] Clustering failed for dataset '{dataset_name}': {e}", flush=True)



# Define the API endpoint for building clusters
@app.post("/build-clusters/")
async def build_clusters_endpoint(request: ClusterRequest, background_tasks: BackgroundTasks):
    if request.num_clusters <= 0:
        raise HTTPException(status_code=400, detail="Number of clusters must be a positive integer.")

    background_tasks.add_task(
        perform_clustering,
        dataset_name=request.dataset_name,
        num_clusters=request.num_clusters,
        use_bert=request.use_bert
    )

    return {"message": f"Clustering for '{request.dataset_name}' started in background using {'BERT' if request.use_bert else 'TF-IDF'}."}

