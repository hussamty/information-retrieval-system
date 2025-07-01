# ui/app.py

from flask import Flask, render_template, request, jsonify
import requests
import mysql.connector
import os
import sys

# إضافة المسار الرئيسي للمشروع لضمان إيجاد config.py
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
    
from config import API_PORTS, DB_CONFIG

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir)

# --- عناوين الخدمات الخلفية ---
SEARCH_API_URL = f"http://127.0.0.1:{API_PORTS['SEARCH']}"

def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error:
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_route():
    data = request.get_json()
    if not data or 'query' not in data or 'dataset_name' not in data:
        return jsonify({"error": "Request body is missing required fields."}), 400

    try:
        response = requests.post(f"{SEARCH_API_URL}/search/", json=data, timeout=120)
        response.raise_for_status()
        search_results = response.json().get('results', [])
    except requests.exceptions.RequestException as e:
        error_message = f"Failed to connect to Search API: {e}"
        if e.response is not None:
            try:
                api_error = e.response.json().get('detail', e.response.text)
                error_message = f"Search API Error ({e.response.status_code}): {api_error}"
            except: pass
        return jsonify({"error": error_message}), 503
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500
    
    if not search_results: return jsonify([])

    doc_ids_scores = {res['doc_id']: res['score'] for res in search_results}
    doc_ids = list(doc_ids_scores.keys())

    cnx = get_db_connection()
    if not cnx: return jsonify({"error": "Could not connect to database."}), 500
    
    try:
        cursor = cnx.cursor(dictionary=True)
        placeholders = ', '.join(['%s'] * len(doc_ids))
        sql = f"SELECT doc_id, original_text FROM documents WHERE doc_id IN ({placeholders}) AND dataset = %s"
        params = doc_ids + [data['dataset_name']]
        cursor.execute(sql, params)
        docs_from_db = cursor.fetchall()
    except mysql.connector.Error as err:
        return jsonify({"error": f"Database query failed: {err}"}), 500
    finally:
        if cnx.is_connected(): cursor.close(); cnx.close()
            
    final_results = []
    for doc in docs_from_db:
        doc['score'] = doc_ids_scores.get(doc['doc_id'], 0)
        final_results.append(doc)
    
    final_results.sort(key=lambda x: x['score'], reverse=True)
    return jsonify(final_results)

# --- Endpoint جديد ومستقل لخدمة اقتراح الاستعلامات ---
@app.route('/suggest/', methods=['GET'])
def suggest_route():
    dataset_name = request.args.get('dataset_name')
    prefix = request.args.get('prefix')

    if not dataset_name or not prefix:
        return jsonify({"error": "dataset_name and prefix are required."}), 400

    try:
        # تمرير الطلب إلى خدمة البحث الفعلية
        response = requests.get(f"{SEARCH_API_URL}/suggest/", params={"dataset_name": dataset_name, "prefix": prefix})
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to get suggestions: {e}"}), 503

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5001, debug=True)

