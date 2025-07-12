# Import necessary libraries
from fastapi import FastAPI, BackgroundTasks # FastAPI for creating the API, BackgroundTasks for running long processes without making the user wait
from pydantic import BaseModel # For creating data models to define the structure of requests
import ir_datasets # A library for easily accessing information retrieval datasets
import mysql.connector # To connect to and interact with a MySQL database
from tqdm import tqdm # To show a progress bar for long loops

# Import custom modules
from core.text_preprocessor import TextPreprocessor 
from config import DB_CONFIG 

# Define the structure of the request body for the /load-dataset/ endpoint
class DatasetRequest(BaseModel):
    # It must contain a string field named 'dataset_name'
    dataset_name: str

# Create a new FastAPI application instance
app = FastAPI(
    # Set the title of the API documentation
    title="Data Loader and Preprocessing API",
    # Set the description of the API documentation (in Arabic)
    description="A service to load datasets from ir_datasets, processing, Storing in Database."
)

# Define the main function that will be run in the background
def process_and_store(dataset_name: str):
    """
    The actual function that runs in the background.
    This version uses batch commits and forced flushing of print statements
    to provide accurate real-time logging.
    """
    # Print a message to the console indicating the task has started. `flush=True` ensures it's displayed immediately.
    print(f"Starting background task for dataset: {dataset_name}", flush=True)
    # Define the number of records to process before saving to the database
    BATCH_SIZE = 10000 
    
    # Use a try...except block to catch any errors during the process
    try:
        # Load the specified dataset using the ir_datasets library
        dataset = ir_datasets.load(dataset_name)
        # Create an instance of our text preprocessor
        preprocessor = TextPreprocessor()
        # Connect to the MySQL database using the configuration
        cnx = mysql.connector.connect(**DB_CONFIG)
        # Create a cursor object to execute SQL queries
        cursor = cnx.cursor()

        # Define the SQL query for inserting or updating data
        sql_insert = (
            # Insert a new row into the 'documents' table
            "INSERT INTO documents (doc_id, dataset, original_text, processed_text) "
            "VALUES (%s, %s, %s, %s) "
            # If a document with the same primary key (doc_id) already exists, update its text fields instead
            "ON DUPLICATE KEY UPDATE original_text=%s, processed_text=%s"
        )

        # Print a status message to the console
        print(f"Processing and storing documents for '{dataset_name}' in batches of {BATCH_SIZE}...", flush=True)
        
        # Initialize a counter for the number of documents processed
        doc_count = 0
        # Loop through each document in the dataset, showing a progress bar with tqdm
        for doc in tqdm(dataset.docs_iter(), total=dataset.docs_count()):
            # Skip documents that don't have a 'text' attribute or have empty text
            if not hasattr(doc, 'text') or not doc.text:
                continue
            
            # Get the original text from the document
            original_text = doc.text
            # Process the text using our preprocessor
            processed_text = preprocessor.preprocess(original_text)
            
            # Execute the SQL insert/update query with the document's data
            cursor.execute(sql_insert, (
                doc.doc_id, dataset_name, original_text, processed_text,
                original_text, processed_text
            ))
            
            # Increment the document counter
            doc_count += 1
            
            # Check if the batch size has been reached
            if doc_count % BATCH_SIZE == 0:
                # Print a message that a batch is being committed
                print(f"\nReached batch size {BATCH_SIZE}. Committing to database...", flush=True)
                # Commit (save) the changes to the database
                cnx.commit()
                # Print a confirmation message
                print(f"  - Commit successful for batch. Total documents processed: {doc_count}", flush=True)

        # After the loop finishes, commit any remaining records that didn't form a full batch
        print("\nLoop finished. Committing final batch...", flush=True)
        # Commit the final changes
        cnx.commit()
        # Print a confirmation message
        print(f"  - Final commit successful. Total documents processed: {doc_count}", flush=True)

        # Close the cursor
        cursor.close()
        # Close the database connection
        cnx.close()
        # Print a final success message
        print(f"Successfully finished processing and storing for '{dataset_name}'.", flush=True)

    # If any exception (error) occurs in the 'try' block
    except Exception as e:
        # Print an error message with the details of the exception
        print(f"\nAn error occurred during processing for '{dataset_name}': {e}", flush=True)


# Define an API endpoint that listens for POST requests at the URL /load-dataset/
@app.post("/load-dataset/")
# This function will be called when a request is received
async def load_dataset_endpoint(request: DatasetRequest, background_tasks: BackgroundTasks):
    # Get the dataset name from the request body
    dataset_name = request.dataset_name
    # Print a message indicating that the request was received
    print(f"Received request to load dataset: {dataset_name}", flush=True)
    # Add the `process_and_store` function to the background tasks to be run
    background_tasks.add_task(process_and_store, dataset_name)
    
    # Immediately return a response to the user
    return {
        "message": f"Data loading and processing for '{dataset_name}' has started in the background."
    }

