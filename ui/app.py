# ui/app.py

# Import necessary libraries
from flask import Flask, render_template, request, jsonify # Flask for the web server, render_template for HTML, request for handling incoming data, jsonify for creating JSON responses
import requests # To make HTTP requests to other APIs (the search API)
import mysql.connector # To connect to the database
import os # For interacting with the operating system (file paths)
import sys # For manipulating the Python path

# Add the project's root directory to the Python path to ensure 'config.py' can be found.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
    
# Import configuration variables from the config file
from config import API_PORTS, DB_CONFIG

# Define the absolute path to the 'templates' directory where index.html is located
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
# Create a Flask application instance, specifying the template and static folders
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# --- Define the URL for the backend search service ---
SEARCH_API_URL = f"http://127.0.0.1:{API_PORTS['SEARCH']}"

# A helper function to establish a database connection
def get_db_connection():
    try:
        # Connect using the credentials from the config file
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error:
        # If the connection fails, return None
        return None

# Define the route for the main page ('/')
@app.route('/')
def index():
    # Render and return the index.html file
    return render_template('index.html')

# Define the route for handling search requests, accepting only POST methods
@app.route('/search', methods=['POST'])
def search_route():
    # Get the JSON data sent from the frontend
    data = request.get_json()
    # Validate that the incoming data has the required fields
    if not data or 'query' not in data or 'dataset_name' not in data:
        return jsonify({"error": "Request body is missing required fields."}), 400 # Return a 400 Bad Request error

    try:
        # Make a POST request to the backend search API, forwarding the JSON data. Set a timeout.
        response = requests.post(f"{SEARCH_API_URL}/search/", json=data, timeout=120)
        # Raise an exception if the API returned an error status code (like 4xx or 5xx)
        response.raise_for_status()
        # Parse the JSON response from the search API and get the list of results
        search_results = response.json().get('results', [])
    except requests.exceptions.RequestException as e:
        # Handle network errors or API errors
        error_message = f"Failed to connect to Search API: {e}"
        if e.response is not None:
            try:
                # Try to get a more specific error message from the API's response
                api_error = e.response.json().get('detail', e.response.text)
                error_message = f"Search API Error ({e.response.status_code}): {api_error}"
            except: pass # If parsing the error response fails, just use the generic message
        return jsonify({"error": error_message}), 503 # Return a 503 Service Unavailable error
    except Exception as e:
        # Handle any other unexpected errors
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500 # Return a 500 Internal Server Error

    # If the search API returned no results, return an empty list
    if not search_results: return jsonify([])

    # The search API returns doc_ids and scores. We need to fetch the actual text from our database.
    # Create a dictionary to map doc_ids to their scores for easy lookup
    doc_ids_scores = {res['doc_id']: res['score'] for res in search_results}
    # Get a list of just the document IDs
    doc_ids = list(doc_ids_scores.keys())

    # Get a connection to the database
    cnx = get_db_connection()
    if not cnx: return jsonify({"error": "Could not connect to database."}), 500
    
    try:
        # Create a cursor to execute queries
        cursor = cnx.cursor(dictionary=True) # dictionary=True makes the cursor return rows as dictionaries
        # Create placeholders for the SQL IN clause to prevent SQL injection
        placeholders = ', '.join(['%s'] * len(doc_ids))
        # The SQL query to fetch the original text for the given doc_ids and dataset
        sql = f"SELECT doc_id, original_text FROM documents WHERE doc_id IN ({placeholders}) AND dataset = %s"
        params = doc_ids + [data['dataset_name']]
        # Execute the query
        cursor.execute(sql, params)
        # Fetch all the matching rows
        docs_from_db = cursor.fetchall()
    except mysql.connector.Error as err:
        # Handle database query errors
        return jsonify({"error": f"Database query failed: {err}"}), 500
    finally:
        # Ensure the connection is closed
        if cnx.is_connected(): cursor.close(); cnx.close()
            
    # Combine the database results (text) with the search API results (score)
    final_results = []
    for doc in docs_from_db:
        # Add the score to the document dictionary
        doc['score'] = doc_ids_scores.get(doc['doc_id'], 0)
        final_results.append(doc)
    
    # Sort the final results by score in descending order, as the order might be lost after the DB query
    final_results.sort(key=lambda x: x['score'], reverse=True)
    # Return the final, combined results as a JSON response
    return jsonify(final_results)

# --- A separate endpoint for handling query suggestions ---
@app.route('/suggest/', methods=['GET'])
def suggest_route():
    # Get the dataset and query from the query parameters in the URL
    dataset_name = request.args.get('dataset_name')
    query = request.args.get('query')

    # Ensure both parameters are provided
    if not dataset_name or query is None: # Check for query's presence, even if it's an empty string
        return jsonify({"error": "dataset_name and query are required."}), 400

    try:
        # Forward the request to the '/suggest/' endpoint of the actual search API
        response = requests.get(f"{SEARCH_API_URL}/suggest/", params={"dataset_name": dataset_name, "query": query})
        response.raise_for_status() # Check for errors
        # Return the JSON response from the search API directly to the frontend
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        # Handle connection errors
        return jsonify({"error": f"Failed to get suggestions: {e}"}), 503

# --- Endpoint for alternative suggestions (spelling correction, query logs) ---
@app.route('/suggest-alternatives/', methods=['GET'])
def suggest_alternatives_route():
    dataset_name = request.args.get('dataset_name')
    query = request.args.get('query')

    if not dataset_name or not query:
        return jsonify({"error": "dataset_name and query are required."}), 400

    try:
        response = requests.get(f"{SEARCH_API_URL}/suggest-alternatives/", params={"dataset_name": dataset_name, "query": query})
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to get alternative suggestions: {e}"}), 503

# Check if the script is run directly (not imported)
if __name__ == '__main__':
    # Start the Flask development server
    app.run(host="0.0.0.0", port=5001, debug=True)

