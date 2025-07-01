import joblib
import os
import sys

# --- الحل: إضافة المسار الرئيسي للمشروع إلى مسار بايثون ---
# هذا هو الجزء الأهم الذي يحل المشكلة
# os.path.abspath(__file__) -> المسار الكامل لهذا الملف
# os.path.dirname(...) -> المسار للمجلد الذي يحتوي على هذا الملف (notebooks)
# os.path.dirname(...) -> المسار للمجلد الرئيسي للمشروع
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
# ----------------------------------------------------

# الآن يمكننا استيراد config بنجاح
from config import MODELS_DIR

# --- باقي الكود يبقى كما هو ---

# حدد مجموعة البيانات التي قمت بتجميعها
dataset_name = 'antique'

# تحميل النتائج
model_dir = os.path.join(MODELS_DIR, dataset_name.replace('/', '_'))
clusters_path = os.path.join(model_dir, 'clusters.joblib')
doc_ids_path = os.path.join(model_dir, 'doc_ids.joblib')

if os.path.exists(clusters_path) and os.path.exists(doc_ids_path):
    clusters = joblib.load(clusters_path)
    doc_ids = joblib.load(doc_ids_path)

    print(f"Clustering results loaded successfully for {dataset_name}.")
    print(f"Total documents: {len(doc_ids)}")
    print(f"Total clusters assigned: {len(clusters)}")

    # عرض العنقود الخاص بأول 10 مستندات كعينة
    print("\n--- Sample Cluster Assignments ---")
    for i in range(10):
        # التأكد من أن الفهرس ضمن النطاق
        if i < len(doc_ids) and i < len(clusters):
            print(f"Document ID '{doc_ids[i]}' is in Cluster: {clusters[i]}")
else:
    print("Error: clusters.joblib or doc_ids.joblib not found. Please run the clustering process first.")


