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
SEARCH_API_URL = f"http://127.0.0.1:{API_PORTS['SEARCH']}/search/"

def get_db_connection():
    """ينشئ اتصالاً بقاعدة البيانات لجلب النصوص الأصلية."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error:
        return None

@app.route('/')
def index():
    """يعرض صفحة البحث الرئيسية."""
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_route():
    """
    يتلقى الطلب من الواجهة، يستدعي خدمة البحث (Search API)،
    ثم يجلب النصوص الأصلية من قاعدة البيانات ويعرض النتائج.
    """
    data = request.get_json()
    
    # --- هذا هو السطر الذي تم تصحيحه ---
    # الآن يتم التحقق من وجود 'dataset_name' بدلاً من 'dataset'
    if not data or 'query' not in data or 'dataset_name' not in data:
        return jsonify({"error": "Request body is missing required fields."}), 400

    # 1. استدعاء خدمة البحث (Search API)
    try:
        # لا حاجة لإنشاء payload جديد، يتم إرسال 'data' مباشرة
        response = requests.post(SEARCH_API_URL, json=data, timeout=120) 
        response.raise_for_status()
        search_results_data = response.json()
        search_results = search_results_data.get('results', [])
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
    
    if not search_results:
        return jsonify([])

    # 2. جلب النصوص الأصلية من قاعدة البيانات
    doc_ids_scores = {res['doc_id']: res['score'] for res in search_results}
    doc_ids = list(doc_ids_scores.keys())

    cnx = get_db_connection()
    if not cnx:
        return jsonify({"error": "Could not connect to database to fetch document text."}), 500
    
    try:
        cursor = cnx.cursor(dictionary=True)
        placeholders = ', '.join(['%s'] * len(doc_ids))
        # استخدام 'dataset_name' هنا أيضاً لضمان التوافق
        sql = f"SELECT doc_id, original_text FROM documents WHERE doc_id IN ({placeholders}) AND dataset = %s"
        params = doc_ids + [data['dataset_name']]
        cursor.execute(sql, params)
        docs_from_db = cursor.fetchall()
    except mysql.connector.Error as err:
        return jsonify({"error": f"Database query failed: {err}"}), 500
    finally:
        if cnx.is_connected():
            cursor.close()
            cnx.close()
            
    # 3. دمج النتائج وإعادة ترتيبها
    final_results = []
    for doc in docs_from_db:
        doc['score'] = doc_ids_scores.get(doc['doc_id'], 0)
        final_results.append(doc)
    
    final_results.sort(key=lambda x: x['score'], reverse=True)
    
    return jsonify(final_results)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5001, debug=True)

